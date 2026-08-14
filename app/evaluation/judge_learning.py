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

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.domain.enums import JudgeMetricId, QuadrantCell
from app.domain.feedback import REJECTION_REASON_LABELS, professor_edits
from app.evaluation.prompts import SYSTEM_PROMPT_FOR
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
    rows = disagreements_for(session, metric)
    if not rows:
        logger.info("No attributable disagreement for %s; prompt left unchanged.", metric.value)
        return None

    repository = JudgePromptRepository(session)
    existing = repository.get(metric)
    current = [
        LearnedJudgeRule.model_validate(rule) for rule in (existing.rules if existing else [])
    ]

    llm = client or get_structured_client()
    learned = llm.complete_structured(
        system=SYSTEM,
        prompt=(
            f"Reviewer: {metric.value}\n\n"
            f"The instruction it currently follows:\n{SYSTEM_PROMPT_FOR[metric]}\n\n"
            f"Rules already learned:\n{json.dumps([r.model_dump() for r in current], indent=2)}\n\n"
            f"Cases where it disagreed with the professor ({len(rows)}):\n"
            f"{_serialize(metric, rows)}\n\n"
            "Return the edited rules."
        ),
        response_model=LearnedJudgeRules,
    )

    row = repository.save(
        metric,
        system_prompt=render_judge_prompt(SYSTEM_PROMPT_FOR[metric], learned.rules),
        note=f"Learned from {len(rows)} disagreement(s).",
        rules=[rule.model_dump() for rule in learned.rules],
        evidence_count=len(rows),
        learned=True,
    )
    session.commit()
    logger.info(
        "Relearned the %s judge from %s disagreements: %s rules (was %s).",
        metric.value,
        len(rows),
        len(learned.rules),
        len(current),
    )
    return row
