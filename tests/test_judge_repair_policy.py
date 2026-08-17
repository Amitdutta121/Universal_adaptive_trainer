"""The policy around a judge repair: when it may run, and what earns adoption.

ADR-042. Separate from ``test_judge_learning.py``, which tests the mechanism
with the policy pinned permissive. These set the policy explicitly, because the
policy is the part that decides whether the loop drifts or climbs.
"""

from __future__ import annotations

from typing import Any

import book_documents as docs
import pytest
from llm_fakes import metric_results
from sqlalchemy.orm import Session

from app.config import get_settings
from app.curriculum import TaxonomyImportService
from app.domain.enums import (
    Difficulty,
    JudgeGate,
    JudgeMetricId,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.evaluation import PedagogicalEvalStatus, PedagogicalEvaluation
from app.evaluation.judge_learning import (
    LearnedJudgeRule,
    LearnedJudgeRules,
    agreements_for,
    refresh_judge_prompt,
    score_prompt,
)
from app.evaluation.prompts import SYSTEM_PROMPT_FOR
from app.feedback import route_review_outcome, submit_review
from app.ingestion import BookImportService
from app.persistence.models import QuestionRow
from app.persistence.repositories import (
    CurriculumRepository,
    JudgePromptRepository,
    QuestionRepository,
)

DIFFICULTY = JudgeMetricId.DIFFICULTY

TAXONOMY = (
    b'{"schema_version":"1","label":"Python","topics":['
    b'{"name":"Loops","subtopics":[{"name":"Counted loops"}]}]}'
)


@pytest.fixture
def grounded(session: Session, settings):
    """A book and an approved taxonomy, so a judge context can be rebuilt."""
    BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    TaxonomyImportService(session, settings).import_upload(filename="tax.json", data=TAXONOMY)
    session.commit()
    version = CurriculumRepository(session).get_approved()
    assert version is not None
    tree = CurriculumRepository(session).get_with_tree(version.id)
    topic = tree.topics[0]
    return {
        "curriculum_version_id": tree.id,
        "topic_id": topic.id,
        "subtopic_ids": [topic.subtopics[0].id],
    }


class Rewriter:
    """Proposes one rule, and records how often it was asked."""

    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    @property
    def description(self) -> str:
        return "fake/rewriter"

    def complete_structured(self, *, system: str, prompt: str, response_model):
        self.calls += 1
        self.prompts.append(prompt)
        return LearnedJudgeRules(rules=[LearnedJudgeRule(rule="A short loop is easy.")])


@pytest.fixture
def rewriter(monkeypatch: pytest.MonkeyPatch) -> Rewriter:
    fake = Rewriter()
    monkeypatch.setattr("app.evaluation.judge_learning.get_structured_client", lambda: fake)
    return fake


def _configure(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for key, value in values.items():
        monkeypatch.setenv(key.upper(), value)
    get_settings.cache_clear()


def _evaluation(gate: JudgeGate, failing: set[JudgeMetricId] | None = None) -> dict[str, Any]:
    return PedagogicalEvaluation(
        status=PedagogicalEvalStatus.COMPLETED,
        gate=gate,
        metrics=metric_results(failing=failing or set()),
        judge_model="fake/judge",
    ).model_dump(mode="json")


def _case(
    session: Session,
    *,
    gate: JudgeGate = JudgeGate.APPROVED,
    decision: ReviewDecision = ReviewDecision.REJECT,
    reasons: list[RejectionReason] | None = None,
    grounding: dict | None = None,
) -> QuestionRow:
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            original_prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            spec={"source_section_ids": [1]},
            pedagogical_eval=_evaluation(gate),
            **(grounding or {}),
        )
    )
    session.commit()
    review = submit_review(
        session,
        question_id=question.id,
        decision=decision,
        reasons=reasons if reasons is not None else [RejectionReason.TOO_EASY],
    )
    session.commit()
    route_review_outcome(session, review)
    session.commit()
    return question


# ------------------------------------------------------------------ threshold


def test_one_disagreement_is_not_enough_to_rewrite(
    session: Session, rewriter: Rewriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rule learned from one case describes that case, not the professor."""
    _configure(monkeypatch, judge_repair_min_disagreements="5", judge_repair_gate_enabled="false")
    _case(session)

    assert refresh_judge_prompt(session, DIFFICULTY) is None
    assert rewriter.calls == 0
    assert JudgePromptRepository(session).get(DIFFICULTY) is None


def test_the_threshold_releases_the_rewrite(
    session: Session, rewriter: Rewriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, judge_repair_min_disagreements="3", judge_repair_gate_enabled="false")
    for _ in range(6):
        _case(session)

    row = refresh_judge_prompt(session, DIFFICULTY)

    assert row is not None
    assert rewriter.calls == 1


# ----------------------------------------------------------------- the gate


MARKER = "CANDIDATE RULE"


class Scorer:
    """A judge whose answer depends on which prompt it was given.

    Every case here is a question claimed ``easy`` that the professor rejected
    as ``too_easy``. So the judge *agrees* with the professor by proposing a
    different difficulty (the claim was wrong) and *disagrees* by proposing
    ``easy`` (endorsing the claim the professor rejected).
    """

    def __init__(self, *, incumbent: Difficulty, candidate: Difficulty) -> None:
        self.incumbent = incumbent
        self.candidate = candidate
        self.scored = 0

    @property
    def description(self) -> str:
        return "fake/judge"

    def complete_structured(self, *, system: str, prompt: str, response_model):
        if response_model is LearnedJudgeRules:
            return LearnedJudgeRules(rules=[LearnedJudgeRule(rule=MARKER)])
        self.scored += 1
        answer = self.candidate if MARKER in system else self.incumbent
        return response_model(difficulty=answer, rationale="because")


def test_a_candidate_that_scores_worse_is_refused(
    session: Session, grounded: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation without selection is drift; this is the selection step."""
    _configure(
        monkeypatch,
        judge_repair_min_disagreements="1",
        judge_repair_gate_enabled="true",
        judge_repair_min_scoring_pairs="1",
        judge_repair_scoring_pairs="4",
    )
    # Question ids divisible by three are held out and become the check set.
    for _ in range(6):
        _case(session, grounding=grounded)

    # The incumbent agrees with the professor (the claim was wrong); the
    # candidate endorses the rejected claim, so it scores strictly worse.
    scorer = Scorer(incumbent=Difficulty.HARD, candidate=Difficulty.EASY)
    monkeypatch.setattr("app.evaluation.judge_learning.get_structured_client", lambda: scorer)

    assert refresh_judge_prompt(session, DIFFICULTY) is None
    assert JudgePromptRepository(session).get(DIFFICULTY) is None
    assert scorer.scored > 0, "the gate must actually run the candidate"


def test_a_candidate_that_holds_the_line_is_adopted(
    session: Session, grounded: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(
        monkeypatch,
        judge_repair_min_disagreements="1",
        judge_repair_gate_enabled="true",
        judge_repair_min_scoring_pairs="1",
        judge_repair_scoring_pairs="4",
    )
    for _ in range(6):
        _case(session, grounding=grounded)

    # The candidate agrees with the professor where the incumbent did not.
    scorer = Scorer(incumbent=Difficulty.EASY, candidate=Difficulty.HARD)
    monkeypatch.setattr("app.evaluation.judge_learning.get_structured_client", lambda: scorer)

    row = refresh_judge_prompt(session, DIFFICULTY)

    assert row is not None
    assert MARKER in row.system_prompt
    assert "Held-out agreement" in (row.note or "")


def test_a_candidate_that_only_ties_is_refused(
    session: Session, grounded: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measured in E3: a rewrite can tie by changing nothing observable at all."""
    _configure(
        monkeypatch,
        judge_repair_min_disagreements="1",
        judge_repair_gate_enabled="true",
        judge_repair_min_scoring_pairs="1",
        judge_repair_scoring_pairs="4",
    )
    for _ in range(6):
        _case(session, grounding=grounded)

    # Both prompts answer identically, so the candidate demonstrates nothing.
    scorer = Scorer(incumbent=Difficulty.HARD, candidate=Difficulty.HARD)
    monkeypatch.setattr("app.evaluation.judge_learning.get_structured_client", lambda: scorer)

    assert refresh_judge_prompt(session, DIFFICULTY) is None
    assert JudgePromptRepository(session).get(DIFFICULTY) is None


def test_too_little_held_out_evidence_refuses_rather_than_guesses(
    session: Session, rewriter: Rewriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unvalidated rewrite is an unmeasured behaviour change, not a small one."""
    _configure(
        monkeypatch,
        judge_repair_min_disagreements="1",
        judge_repair_gate_enabled="true",
        judge_repair_min_scoring_pairs="5",
    )
    _case(session)

    assert refresh_judge_prompt(session, DIFFICULTY) is None
    assert JudgePromptRepository(session).get(DIFFICULTY) is None


def test_scoring_counts_per_metric_agreement(
    session: Session, grounded: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cell agreement would hide a judge that was wrong inside an agreed cell."""
    _configure(monkeypatch, judge_repair_min_disagreements="1")
    _case(session, grounding=grounded)
    from app.persistence.repositories import ReviewOutcomeRepository

    pairs = ReviewOutcomeRepository(session).list_recent()

    # Endorsing the claim the professor rejected is a disagreement...
    endorsing = Scorer(incumbent=Difficulty.EASY, candidate=Difficulty.EASY)
    agreed, scored = score_prompt(
        session, DIFFICULTY, SYSTEM_PROMPT_FOR[DIFFICULTY], pairs, client=endorsing
    )
    assert scored == len(pairs)
    assert agreed == 0

    # ...and contradicting it is an agreement.
    contradicting = Scorer(incumbent=Difficulty.HARD, candidate=Difficulty.HARD)
    agreed, scored = score_prompt(
        session, DIFFICULTY, SYSTEM_PROMPT_FOR[DIFFICULTY], pairs, client=contradicting
    )
    assert agreed == scored == len(pairs)


# --------------------------------------------------------- balanced evidence


def test_the_rewriter_is_shown_cases_the_judge_got_right(
    session: Session, rewriter: Rewriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Errors alone give no base rate, so correct behaviour gets broken to fix a rare fault."""
    _configure(monkeypatch, judge_repair_min_disagreements="1", judge_repair_gate_enabled="false")
    _case(session)
    _case(session, gate=JudgeGate.APPROVED, decision=ReviewDecision.APPROVE, reasons=[])

    refresh_judge_prompt(session, DIFFICULTY)

    assert "AGREED with the professor" in rewriter.prompts[0]


def test_agreements_are_drawn_from_the_agreeing_cells(session: Session) -> None:
    _case(session, gate=JudgeGate.APPROVED, decision=ReviewDecision.APPROVE, reasons=[])
    _case(session)

    kept = agreements_for(session, DIFFICULTY, limit=10)

    assert kept
    assert all(row.cell.value in ("confirmed_good", "confirmed_bad") for row in kept)


# ------------------------------------------------------------ freeze switches


def test_learning_can_be_frozen_for_a_clean_measurement(
    client, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A judge cannot be measured while the generator is also moving."""
    _configure(monkeypatch, judge_learning_enabled="false", generator_learning_enabled="false")
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            original_prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(JudgeGate.APPROVED),
        )
    )
    session.commit()

    body = client.post(
        f"/api/questions/{question.id}/review",
        json={"decision": "reject", "reasons": ["too_easy"]},
    ).json()

    # The outcome is still recorded -- freezing stops learning, not measurement.
    assert body["outcome"]["cell"] == "missed"
    assert body["outcome"]["judges_refreshed"] == []
    assert body["outcome"]["instruction_refreshed"] is False
