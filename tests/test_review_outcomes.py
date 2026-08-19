"""Routing a review to its quadrant cell the moment it lands (ADR-037).

The four cells each call for something different, and these check that the call
is made per review rather than only when someone opens the calibration page:
both-rejected relearns the type instruction, the two disagreeing cells name the
judge at fault, and every placeable review is written to the dataset.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from llm_fakes import metric_results
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.enums import (
    CalibrationLabel,
    Difficulty,
    JudgeGate,
    JudgeMetricId,
    QuadrantCell,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.errors import LLMRequestError
from app.evaluation import PedagogicalEvalStatus, PedagogicalEvaluation
from app.feedback import route_review_outcome, submit_review
from app.persistence.models import QuestionRow
from app.persistence.repositories import (
    ProfessorReviewRepository,
    QuestionRepository,
    ReviewOutcomeRepository,
    TypeInstructionRepository,
)
from app.personalization import LearnedRule, LearnedRules


class Rewriter:
    """Stands in for the instruction rewriter, counting how often it is called."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    @property
    def description(self) -> str:
        return "fake/rewriter"

    def complete_structured(self, *, system: str, prompt: str, response_model: type[BaseModel]):
        self.calls += 1
        if self.fail:
            raise LLMRequestError("The provider is unavailable.", detail="502 from provider")
        return LearnedRules(rules=[LearnedRule(rule="Name the defect in the prompt.")])


@pytest.fixture
def rewriter(monkeypatch: pytest.MonkeyPatch) -> Rewriter:
    """Intercept the model call the confirmed-bad cell makes."""
    fake = Rewriter()
    monkeypatch.setattr("app.personalization.instructions.get_structured_client", lambda: fake)
    return fake


def _evaluation(
    gate: JudgeGate,
    *,
    failing: set[JudgeMetricId] | None = None,
    status: PedagogicalEvalStatus = PedagogicalEvalStatus.COMPLETED,
) -> dict[str, Any]:
    if failing is None:
        failing = set(JudgeMetricId) if gate is JudgeGate.REJECT else set()
    return PedagogicalEvaluation(
        status=status,
        gate=gate,
        metrics=metric_results(failing=failing),
        judge_model="fake/judge",
        rubric_version="question-metrics@1",
    ).model_dump(mode="json")


def _question(
    session: Session,
    *,
    evaluation: dict[str, Any] | None,
    question_type: QuestionType | None = QuestionType.MULTIPLE_CHOICE,
) -> QuestionRow:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Which statement about strings is true?",
            original_prompt="Which statement about strings is true?",
            reference_solution="",
            tests="",
            question_type=question_type,
            difficulty=Difficulty.MEDIUM,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=evaluation,
        )
    )
    session.commit()
    return row


def _review(
    session: Session,
    question: QuestionRow,
    decision: ReviewDecision,
    *,
    reasons: list[RejectionReason] | None = None,
):
    review = submit_review(
        session,
        question_id=question.id,
        decision=decision,
        reasons=reasons,
        prompt="Which statement about immutability is true?"
        if decision is ReviewDecision.EDIT
        else None,
        reference_solution="" if decision is ReviewDecision.EDIT else None,
        tests="" if decision is ReviewDecision.EDIT else None,
    )
    session.commit()
    return review


# ------------------------------------------------------------------ the four cells


@pytest.mark.parametrize(
    ("gate", "decision", "expected"),
    [
        (JudgeGate.APPROVED, ReviewDecision.APPROVE, QuadrantCell.CONFIRMED_GOOD),
        (JudgeGate.APPROVED, ReviewDecision.REJECT, QuadrantCell.MISSED),
        (JudgeGate.REJECT, ReviewDecision.APPROVE, QuadrantCell.FALSE_ALARM),
        (JudgeGate.REJECT, ReviewDecision.REJECT, QuadrantCell.CONFIRMED_BAD),
    ],
)
def test_each_review_lands_in_its_cell(
    session: Session, gate: JudgeGate, decision: ReviewDecision, expected: QuadrantCell
) -> None:
    question = _question(session, evaluation=_evaluation(gate))
    review = _review(
        session,
        question,
        decision,
        reasons=[RejectionReason.TOO_EASY] if decision is ReviewDecision.REJECT else None,
    )

    outcome = route_review_outcome(session, review)

    assert outcome is not None
    assert outcome.cell is expected


def test_an_edit_counts_as_the_professor_not_accepting(session: Session) -> None:
    question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))
    review = _review(session, question, ReviewDecision.EDIT)

    outcome = route_review_outcome(session, review)

    assert outcome is not None
    assert outcome.professor is CalibrationLabel.NEEDS_REVIEW
    assert outcome.cell is QuadrantCell.MISSED


def test_the_outcome_is_written_to_the_dataset(session: Session) -> None:
    question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))
    review = _review(session, question, ReviewDecision.APPROVE)

    route_review_outcome(session, review)
    session.commit()

    stored = ReviewOutcomeRepository(session).get_for_review(review.id)
    assert stored is not None
    assert stored.question_id == question.id
    assert stored.cell is QuadrantCell.CONFIRMED_GOOD
    assert stored.question_type is QuestionType.MULTIPLE_CHOICE
    assert stored.rubric_version == "question-metrics@1"


def test_the_dataset_row_freezes_the_verdict_against_a_later_re_judge(session: Session) -> None:
    """A bulk re-judge must not silently restate what the judge said back then."""
    question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))
    review = _review(session, question, ReviewDecision.APPROVE)
    route_review_outcome(session, review)
    session.commit()

    question.pedagogical_eval = _evaluation(JudgeGate.REJECT)
    session.commit()

    stored = ReviewOutcomeRepository(session).get_for_review(review.id)
    assert stored is not None
    assert stored.judge is CalibrationLabel.ACCEPT
    assert stored.cell is QuadrantCell.CONFIRMED_GOOD


def test_routing_twice_does_not_double_count(session: Session) -> None:
    question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))
    review = _review(session, question, ReviewDecision.APPROVE)

    first = route_review_outcome(session, review)
    second = route_review_outcome(session, review)
    session.commit()

    assert first is not None and second is not None
    assert first.row.id == second.row.id
    assert len(ReviewOutcomeRepository(session).list_recent()) == 1


# ---------------------------------------------------------------- naming the judge


def test_a_missed_review_names_the_judge_that_passed_it(session: Session) -> None:
    question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))
    review = _review(session, question, ReviewDecision.REJECT, reasons=[RejectionReason.TOO_EASY])

    outcome = route_review_outcome(session, review)

    assert outcome is not None
    assert outcome.attributed_metrics == [JudgeMetricId.DIFFICULTY]


def test_a_false_alarm_names_the_judge_that_flagged_it(session: Session) -> None:
    question = _question(
        session,
        evaluation=_evaluation(JudgeGate.REJECT, failing={JudgeMetricId.SUBTOPIC}),
    )
    # Gate REJECT with only one failing metric is what a re-judge can store; the
    # cell is decided by the gate, and attribution by the individual metrics.
    review = _review(session, question, ReviewDecision.APPROVE)

    outcome = route_review_outcome(session, review)

    assert outcome is not None
    assert outcome.attributed_metrics == [JudgeMetricId.SUBTOPIC]


def test_an_edit_without_reasons_is_recorded_as_unattributed(session: Session) -> None:
    """The honest answer when the professor cited nothing to compare against."""
    question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))
    review = _review(session, question, ReviewDecision.EDIT)

    outcome = route_review_outcome(session, review)

    assert outcome is not None
    assert outcome.cell is QuadrantCell.MISSED
    assert outcome.attributed_metrics == []


def test_the_agreeing_cells_attribute_no_fault(session: Session) -> None:
    question = _question(session, evaluation=_evaluation(JudgeGate.REJECT))
    review = _review(session, question, ReviewDecision.REJECT, reasons=[RejectionReason.AMBIGUOUS])

    outcome = route_review_outcome(session, review)

    assert outcome is not None
    assert outcome.cell is QuadrantCell.CONFIRMED_BAD
    assert outcome.attributed_metrics == []


def test_the_held_out_third_is_marked_at_write_time(session: Session) -> None:
    placed = []
    for _ in range(3):
        question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))
        review = _review(session, question, ReviewDecision.APPROVE)
        outcome = route_review_outcome(session, review)
        session.commit()
        assert outcome is not None
        placed.append((question.id, outcome.held_out))

    assert [held for _, held in placed] == [question_id % 3 == 0 for question_id, _ in placed]
    assert any(held for _, held in placed)


# -------------------------------------------------------------- unplaceable reviews


@pytest.mark.parametrize(
    "evaluation",
    [
        None,
        {"not": "an evaluation"},
    ],
    ids=["no evaluation", "unreadable evaluation"],
)
def test_a_question_without_a_usable_verdict_is_not_placed(
    session: Session, evaluation: dict[str, Any] | None
) -> None:
    question = _question(session, evaluation=evaluation)
    review = _review(session, question, ReviewDecision.APPROVE)

    assert route_review_outcome(session, review) is None
    assert ReviewOutcomeRepository(session).list_recent() == []


def test_a_skipped_judge_is_not_a_disagreement(session: Session) -> None:
    """Deterministic validation failed, so no judge ran and none can be wrong."""
    question = _question(
        session,
        evaluation=PedagogicalEvaluation(
            status=PedagogicalEvalStatus.SKIPPED, skip_reason="deterministic_failed"
        ).model_dump(mode="json"),
    )
    review = _review(session, question, ReviewDecision.REJECT, reasons=[RejectionReason.AMBIGUOUS])

    assert route_review_outcome(session, review) is None


def test_a_partial_evaluation_is_not_placed(session: Session) -> None:
    question = _question(
        session,
        evaluation=_evaluation(JudgeGate.APPROVED, status=PedagogicalEvalStatus.PARTIAL),
    )
    review = _review(session, question, ReviewDecision.APPROVE)

    assert route_review_outcome(session, review) is None


# ------------------------------------------------------- the confirmed-bad cell acts


def _reject_through_the_api(client: TestClient, question_id: int) -> dict[str, Any]:
    response = client.post(
        f"/api/questions/{question_id}/review",
        json={"decision": "reject", "reasons": ["ambiguous"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_both_rejecting_relearns_the_instruction_on_submit(
    client: TestClient, session: Session, rewriter: Rewriter
) -> None:
    question = _question(session, evaluation=_evaluation(JudgeGate.REJECT))

    body = _reject_through_the_api(client, question.id)

    assert body["outcome"]["cell"] == QuadrantCell.CONFIRMED_BAD.value
    assert body["outcome"]["instruction_refreshed"] is True
    assert body["outcome"]["refresh_rule_count"] == 1
    assert rewriter.calls == 1

    stored = TypeInstructionRepository(session).get(QuestionType.MULTIPLE_CHOICE)
    assert stored is not None
    assert "Name the defect in the prompt." in stored.instruction


def test_a_missed_review_teaches_the_generator_and_the_judge(
    client: TestClient, session: Session, rewriter: Rewriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two things went wrong, so two things learn."""
    judge_calls: list[str] = []
    monkeypatch.setattr(
        "app.web.routes.api.feedback.refresh_judge_prompt",
        lambda _session, metric: judge_calls.append(metric.value) or object(),
    )
    question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))

    body = client.post(
        f"/api/questions/{question.id}/review",
        json={"decision": "reject", "reasons": ["too_easy"]},
    ).json()

    assert body["outcome"]["cell"] == QuadrantCell.MISSED.value
    # The generator wrote a question the professor rejected...
    assert body["outcome"]["instruction_refreshed"] is True
    assert rewriter.calls == 1
    # ...and the judge passed it.
    assert judge_calls == [JudgeMetricId.DIFFICULTY.value]


def test_a_false_alarm_teaches_only_the_judge(
    client: TestClient, session: Session, rewriter: Rewriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The professor approved it, so the generator did nothing wrong."""
    monkeypatch.setattr(
        "app.web.routes.api.feedback.refresh_judge_prompt", lambda _session, _metric: object()
    )
    question = _question(session, evaluation=_evaluation(JudgeGate.REJECT))

    body = client.post(f"/api/questions/{question.id}/review", json={"decision": "approve"}).json()

    assert body["outcome"]["cell"] == QuadrantCell.FALSE_ALARM.value
    assert body["outcome"]["instruction_refreshed"] is False
    assert rewriter.calls == 0


def test_the_other_cells_spend_no_model_call(
    client: TestClient, session: Session, rewriter: Rewriter
) -> None:
    question = _question(session, evaluation=_evaluation(JudgeGate.APPROVED))

    response = client.post(f"/api/questions/{question.id}/review", json={"decision": "approve"})

    assert response.status_code == 201
    assert response.json()["outcome"]["cell"] == QuadrantCell.CONFIRMED_GOOD.value
    assert rewriter.calls == 0


def test_a_failed_refresh_keeps_the_review_and_reports_it(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verdict is the professor's work; a provider outage must not discard it."""
    failing = Rewriter(fail=True)
    monkeypatch.setattr("app.personalization.instructions.get_structured_client", lambda: failing)
    question = _question(session, evaluation=_evaluation(JudgeGate.REJECT))

    body = _reject_through_the_api(client, question.id)

    assert body["outcome"]["instruction_refreshed"] is False
    assert "provider" in (body["outcome"]["refresh_error"] or "").lower()

    session.expire_all()
    assert ProfessorReviewRepository(session).count() == 1
    stored = ReviewOutcomeRepository(session).get_for_review(body["id"])
    assert stored is not None
    assert stored.instruction_refreshed is False
    assert stored.refresh_error
