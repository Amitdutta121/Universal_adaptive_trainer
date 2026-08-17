"""Learn a judge's prompt from the questions it got wrong (ADR-039).

The mirror image of :mod:`app.personalization.instructions`. That module learns
what the *generator* is told from the professor's reviews; this one learns what a
*judge* is told from the disagreements between that judge and the professor.

The two are deliberately built the same way, for the same measured reason:

* **Rules accumulate.** The rewriter is shown the rules it already has and
  returns them edited, with new ones appended and obsolete ones dropped. ADR-033
  recorded what happens otherwise -- rewriting from scratch each round loses
  lessons earned three rounds ago.
* **The shipped prompt stays.** Learned rules are rendered *onto* it, never
  instead of it. The shipped text carries the contract: which issue codes exist,
  what the difficulty bands mean, what to return. A free rewrite would be free to
  drop the code list, after which the judge answers in a vocabulary the professor
  does not share and per-metric calibration stops comparing anything.

What differs from personalization is the evidence and the guard. The evidence is
disagreement rows (ADR-037), not reviews, and the **held-out third is excluded**
(ADR-035): a judge tuned on the questions it is later scored against reports its
own fitting as improvement.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.calibration.schema import PROFESSOR_OBJECTIONS
from app.config import Settings, get_settings
from app.domain.enums import JudgeMetricId, QuadrantCell
from app.domain.feedback import REJECTION_REASON_LABELS, professor_edits
from app.domain.questions import Question
from app.errors import AdaptiveTrainerError
from app.evaluation.prompts import SYSTEM_PROMPT_FOR, build_user_prompt
from app.evaluation.schema import RESPONSE_MODEL_FOR
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import JudgePromptRow, ReviewOutcomeRow
from app.persistence.repositories import JudgePromptRepository, ReviewOutcomeRepository

logger = logging.getLogger(__name__)

#: Disagreements sent to the rewriter. Enough to show a pattern without paying
#: for the whole history on every refresh. Matches personalization's limit.
DISAGREEMENT_LIMIT = 60

#: Characters of a question kept when quoting it as evidence.
SNIPPET_CHARS = 240

SYSTEM = (
    "You maintain the instruction ONE automated reviewer follows when it judges "
    "introductory-Python assessment questions. You are given the rules it has already "
    "learned and the cases where it disagreed with the professor. Each case says what "
    "the reviewer decided, what it said, and what the professor decided. Return the "
    "rules edited: keep the ones the evidence still supports, reword one that is vague, "
    "add one for a disagreement not yet covered, and drop one the evidence no longer "
    "supports. Every rule must be a concrete decision rule the reviewer can apply to the "
    "next question -- say what to count as a fault and what not to, not what to be. Do "
    "not restate the reviewer's existing instructions. Do not invent a standard the "
    "professor has not shown. Cite the question ids each rule comes from."
)


class LearnedJudgeRule(BaseModel):
    """One decision rule the disagreements justify."""

    rule: str = Field(min_length=1, description="A concrete, applicable decision rule.")
    question_ids: list[int] = Field(
        default_factory=list, description="Questions that justify this rule."
    )


class LearnedJudgeRules(BaseModel):
    rules: list[LearnedJudgeRule] = Field(default_factory=list)


def render_judge_prompt(base: str, rules: list[LearnedJudgeRule]) -> str:
    """Combine the shipped judge prompt with the learned rules.

    The shipped text stays first and whole: it is the contract, not a preference.
    """
    if not rules:
        return base
    lines = [base, "", "Calibration to this professor, learned from cases you got wrong:"]
    lines.extend(f"- {rule.rule}" for rule in rules)
    return "\n".join(lines)


def _serialize(metric: JudgeMetricId, rows: list[ReviewOutcomeRow]) -> str:
    """Describe each disagreement from the judge's point of view.

    Two fields are deliberately historical rather than current:

    ``you_said`` is the rationale snapshotted when the review landed, not the
    question's current evaluation. A bulk re-judge may have replaced that, and
    showing a later opinion as the one the professor contradicted would ask the
    rewriter to fix something that was never said.

    ``question`` is ``original_prompt`` -- the text the judge actually saw. An
    ``edit`` overwrites ``prompt`` with the professor's corrected version, so
    quoting the current text would show the rewriter a fixed question and ask why
    the judge passed it. The correction is given separately as
    ``professor_rewrote_it_as``, where it is evidence rather than a
    contradiction: the difference between the two is precisely what the judge
    failed to notice.
    """
    cases = []
    for row in rows:
        review = row.review
        question = row.question
        rationale = (row.judge_rationales or {}).get(metric.value)
        judged_text = (question.original_prompt or question.prompt) if question else None
        edits = (
            professor_edits(
                changed_fields=list(review.changed_fields or []),
                edited_prompt=review.edited_prompt,
                edited_reference_solution=review.edited_reference_solution,
                edited_tests=review.edited_tests,
                limit=SNIPPET_CHARS,
            )
            if review
            else {}
        )
        cases.append(
            {
                "question_id": row.question_id,
                "your_verdict": ("passed" if row.cell is QuadrantCell.MISSED else "failed"),
                "you_said": rationale,
                "professor_decision": str(review.decision) if review else None,
                "professor_reasons": (
                    [REJECTION_REASON_LABELS[reason] for reason in review.reasons] if review else []
                ),
                "professor_comment": ((review.comment or "").strip() or None) if review else None,
                "question": (judged_text or "")[:SNIPPET_CHARS] or None,
                # Only the fields the professor really changed. The difference
                # between the question and the correction is what this judge
                # failed to notice, so naming the wrong field would point the
                # rewrite at something nobody touched.
                "professor_corrected": edits or None,
                "claimed_difficulty": (
                    str(question.difficulty) if question and question.difficulty else None
                ),
            }
        )
    return json.dumps(cases, separators=(",", ":"))


def disagreements_for(session: Session, metric: JudgeMetricId) -> list[ReviewOutcomeRow]:
    """The cases this judge may learn from: its own faults, minus the held-out third."""
    return ReviewOutcomeRepository(session).list_disagreements_for(
        metric, include_held_out=False, limit=DISAGREEMENT_LIMIT
    )


def agreements_for(
    session: Session, metric: JudgeMetricId, *, limit: int
) -> list[ReviewOutcomeRow]:
    """Cases this judge got *right*, as a counterweight to its failures.

    A judge shown only its errors has no base rate: it cannot tell being wrong
    ten times out of twenty from ten times out of five hundred, and will break
    correct behaviour to fix a rare fault. Continual-learning practice calls the
    fix a replay buffer; here it is simply a sample of the agreeing cells.
    """
    rows = ReviewOutcomeRepository(session).list_in_cells(
        [QuadrantCell.CONFIRMED_GOOD, QuadrantCell.CONFIRMED_BAD],
        include_held_out=False,
        limit=limit,
    )
    return rows[:limit]


def score_prompt(
    session: Session,
    metric: JudgeMetricId,
    system_prompt: str,
    pairs: list[ReviewOutcomeRow],
    *,
    client: StructuredLLMClient,
) -> tuple[int, int]:
    """Run one candidate prompt over labelled pairs; return (agreements, scored).

    Agreement is per metric, not per cell: the professor objected on one of this
    judge's own reasons, or they did not, and the judge either flagged it or did
    not. Cell agreement would hide a judge that was wrong inside a question the
    two sides happened to agree about overall.

    A pair whose context cannot be rebuilt, or whose call fails, is skipped
    rather than counted as a failure -- an absent measurement is not evidence
    against the candidate.
    """
    from app.evaluation.service import build_judge_context, result_from_verdict

    owned = PROFESSOR_OBJECTIONS.get(metric, frozenset())
    agreements = 0
    scored = 0
    for row in pairs:
        question_row = row.question
        review = row.review
        if question_row is None or review is None:
            continue
        try:
            question = Question.model_validate(question_row)
            context = build_judge_context(session, question)
            verdict = client.complete_structured(
                system=system_prompt,
                prompt=build_user_prompt(metric, context),
                response_model=RESPONSE_MODEL_FOR[metric],
            )
            result = result_from_verdict(metric, verdict, question)
        except (AdaptiveTrainerError, LookupError, TypeError, ValueError) as exc:
            logger.warning("Scoring skipped question %s for %s: %s", row.question_id, metric, exc)
            continue
        if result.passed is None:
            continue
        objected = bool(set(review.reasons or []) & owned)
        agreements += int(result.passed is not objected)
        scored += 1
    return agreements, scored


def refresh_judge_prompt(
    session: Session,
    metric: JudgeMetricId,
    *,
    client: StructuredLLMClient | None = None,
) -> JudgePromptRow | None:
    """Re-learn one judge's prompt from the questions it got wrong.

    Returns ``None`` when no attributable disagreement exists yet, leaving the
    prompt in place. A judge nobody has contradicted has nothing to learn from,
    and inventing rules for it would make it worse in an unmeasured direction.

    A prompt the professor typed by hand is **not** overwritten silently: its
    rules are empty, so the rewriter starts from the shipped text plus whatever
    it learns, and the hand-written text would be lost. Callers that may hit a
    hand-edited judge check :attr:`JudgePromptRow.learned` first.
    """
    settings = get_settings()
    rows = disagreements_for(session, metric)
    if len(rows) < settings.judge_repair_min_disagreements:
        logger.info(
            "Only %s disagreement(s) for %s; %s needed. Prompt left unchanged.",
            len(rows),
            metric.value,
            settings.judge_repair_min_disagreements,
        )
        return None

    repository = JudgePromptRepository(session)
    existing = repository.get(metric)
    current = [
        LearnedJudgeRule.model_validate(rule) for rule in (existing.rules if existing else [])
    ]
    incumbent = existing.system_prompt if existing else SYSTEM_PROMPT_FOR[metric]
    kept = agreements_for(session, metric, limit=len(rows))

    llm = client or get_structured_client()
    learned = llm.complete_structured(
        system=SYSTEM,
        prompt=(
            f"Reviewer: {metric.value}\n\n"
            f"The instruction it currently follows:\n{SYSTEM_PROMPT_FOR[metric]}\n\n"
            f"Rules already learned:\n{json.dumps([r.model_dump() for r in current], indent=2)}\n\n"
            f"Cases where it disagreed with the professor ({len(rows)}):\n"
            f"{_serialize(metric, rows)}\n\n"
            f"Cases where it AGREED with the professor, which your rules must not "
            f"break ({len(kept)}):\n{_serialize(metric, kept)}\n\n"
            "Return the edited rules."
        ),
        response_model=LearnedJudgeRules,
    )

    candidate = render_judge_prompt(SYSTEM_PROMPT_FOR[metric], learned.rules)
    verdict = _gate(session, metric, incumbent, candidate, client=llm, settings=settings)
    if not verdict.accepted:
        logger.info("Rewritten %s judge refused: %s", metric.value, verdict.detail)
        return None

    row = repository.save(
        metric,
        system_prompt=candidate,
        note=f"Learned from {len(rows)} disagreement(s). {verdict.detail}",
        rules=[rule.model_dump() for rule in learned.rules],
        evidence_count=len(rows),
        learned=True,
    )
    session.commit()
    logger.info(
        "Relearned the %s judge from %s disagreements: %s rules (was %s). %s",
        metric.value,
        len(rows),
        len(learned.rules),
        len(current),
        verdict.detail,
    )
    return row


@dataclass(frozen=True)
class GateVerdict:
    """Whether a rewritten judge earned adoption, and on what evidence."""

    accepted: bool
    detail: str


def _gate(
    session: Session,
    metric: JudgeMetricId,
    incumbent: str,
    candidate: str,
    *,
    client: StructuredLLMClient,
    settings: Settings,
) -> GateVerdict:
    """Adopt a rewritten judge only if it does not lose on the held-out pairs.

    Refuses rather than applies when there is too little held-out evidence to
    tell an improvement from noise. That deliberately means a young installation
    learns nothing: an unvalidated rewrite is not a smaller version of a
    validated one, it is an unmeasured behaviour change.

    **A tie is a refusal.** This was measured (E3, ADR-042): a reflective
    rewrite, the shipped prompt and an eight-example few-shot prompt all scored
    8/12 on the same held-out set *and produced identical error sets*. A tying
    candidate is not a candidate that held its ground -- it is one that changed
    nothing that could be observed. Adopting it would still re-name the panel,
    fragmenting the evidence that any later figure has to accumulate under one
    version.
    """
    if not settings.judge_repair_gate_enabled:
        return GateVerdict(accepted=True, detail="Gate disabled; adopted unscored.")

    pairs = ReviewOutcomeRepository(session).list_held_out(
        limit=settings.judge_repair_scoring_pairs
    )
    if len(pairs) < settings.judge_repair_min_scoring_pairs:
        return GateVerdict(
            accepted=False,
            detail=(
                f"Only {len(pairs)} held-out pair(s); "
                f"{settings.judge_repair_min_scoring_pairs} needed to score a rewrite."
            ),
        )

    before, n_before = score_prompt(session, metric, incumbent, pairs, client=client)
    after, n_after = score_prompt(session, metric, candidate, pairs, client=client)
    if n_before == 0 or n_after == 0:
        return GateVerdict(accepted=False, detail="No held-out pair could be scored.")

    rate_before = before / n_before
    rate_after = after / n_after
    detail = (
        f"Held-out agreement {before}/{n_before} ({rate_before:.0%}) -> "
        f"{after}/{n_after} ({rate_after:.0%})."
    )
    return GateVerdict(accepted=rate_after > rate_before, detail=detail)
