"""Reviews return at once; a lesson run at the start of each round learns from them (ADR-063, m1).

A review only records its outcome, with ``lessons_round_id`` unset. The next round's job
relearns each affected type and judge once, marks the rows it learned from, and states on
the round how many it applied -- or why it could not, without failing the round.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from llm_fakes import MetricJudgeClient, metric_results
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import (
    Difficulty,
    JudgeGate,
    JudgeMetricId,
    QuadrantCell,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
    RoundStatus,
)
from app.errors import LLMRequestError
from app.evaluation import PedagogicalEvalStatus, PedagogicalEvaluation
from app.feedback import route_review_outcome, submit_review
from app.feedback.lessons import apply_pending_lessons
from app.persistence.models import CourseRow, CurriculumVersionRow, QuestionRow, ReviewOutcomeRow
from app.persistence.repositories import QuestionRepository, ReviewOutcomeRepository
from app.subjects import PYTHON_PROFILE
from app.web.routes.api.schemas import GenerationRoundOut
from tests import test_rounds
from tests.test_rounds import _mcq, _queue, _round, _run, _setup, _target

env = test_rounds.env
fake_library = test_rounds.fake_library

MC = QuestionType.MULTIPLE_CHOICE


class NoModel:
    """A structured client that fails the test if anything asks it for an answer."""

    description = "fake/no-model"

    def complete_structured(self, **_kwargs: Any):
        raise AssertionError("a review must not call a model")


def _evaluation(gate: JudgeGate) -> dict[str, Any]:
    failing = set(JudgeMetricId) if gate is JudgeGate.REJECT else set()
    return PedagogicalEvaluation(
        status=PedagogicalEvalStatus.COMPLETED,
        gate=gate,
        metrics=metric_results(failing=failing),
        judge_model="fake/judge",
    ).model_dump(mode="json")


def _question(
    session: Session, *, gate: JudgeGate, version_id: int | None = None, qtype=MC
) -> QuestionRow:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Which loop repeats while a condition holds?",
            original_prompt="Which loop repeats while a condition holds?",
            question_type=qtype,
            difficulty=Difficulty.MEDIUM,
            status=QuestionStatus.VALIDATION_PASSED,
            curriculum_version_id=version_id,
            pedagogical_eval=_evaluation(gate),
        )
    )
    session.commit()
    return row


def _reject(session: Session, question: QuestionRow) -> ReviewOutcomeRow:
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.AMBIGUOUS],
    )
    outcome = route_review_outcome(session, review)
    session.commit()
    assert outcome is not None
    return outcome.row


def _outcomes(engine: Engine) -> list[ReviewOutcomeRow]:
    with Session(engine) as fresh:
        return ReviewOutcomeRepository(fresh).list_recent()


def _round_client(env: SimpleNamespace) -> MetricJudgeClient:
    return MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id), difficulty=Difficulty.MEDIUM
    )


class TypeRefreshes:
    """Stands in for ``distill_guidelines``, counting calls per type."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[QuestionType] = []
        self.fail = fail

    def __call__(self, _session: Session, *, question_type: QuestionType, **_kwargs: Any):
        self.calls.append(question_type)
        if self.fail:
            raise LLMRequestError("The provider is unavailable.", detail="502 from provider")
        return SimpleNamespace(changed=True)


# ------------------------------------------------------------------ a review only records


@pytest.mark.parametrize(
    ("gate", "decision"),
    [
        (JudgeGate.APPROVED, "reject"),  # missed: used to relearn generator and judge
        (JudgeGate.REJECT, "reject"),  # confirmed bad: used to relearn the generator
        (JudgeGate.REJECT, "approve"),  # false alarm: used to relearn the judge
    ],
)
def test_a_review_makes_no_model_call_and_leaves_its_lesson_pending(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    gate: JudgeGate,
    decision: str,
) -> None:
    monkeypatch.setattr("app.memory.guidelines.get_structured_client", NoModel)
    monkeypatch.setattr("app.evaluation.judge_learning.get_structured_client", NoModel)
    monkeypatch.setattr("app.llm.get_structured_client", NoModel)
    question = _question(session, gate=gate)

    body: dict[str, Any] = {"decision": decision}
    if decision == "reject":
        body["reasons"] = ["too_easy"]
    response = client.post(f"/api/questions/{question.id}/review", json=body)

    assert response.status_code == 201, response.text
    assert response.json()["outcome"]["instruction_refreshed"] is False
    assert response.json()["outcome"]["judges_refreshed"] == []
    session.expire_all()
    stored = ReviewOutcomeRepository(session).get_for_review(response.json()["id"])
    assert stored is not None
    assert stored.lessons_round_id is None


# ------------------------------------------------------------------ the lesson run


def test_three_rejects_of_one_type_relearn_it_once_at_the_next_round(
    session: Session, engine: Engine, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    refreshes = TypeRefreshes()
    monkeypatch.setattr("app.feedback.lessons.distill_guidelines", refreshes)
    for _ in range(3):
        _reject(session, _question(session, gate=JudgeGate.REJECT, version_id=env.version.id))
    assert [row.lessons_round_id for row in _outcomes(engine)] == [None, None, None]

    setup = _setup(session, env, [(env.while_loops.id, "medium", 1)])
    row = _queue(session, setup, [_target(env)])
    _run(engine, row.id, _round_client(env))

    assert refreshes.calls == [MC]
    outcomes = _outcomes(engine)
    assert [o.lessons_round_id for o in outcomes] == [row.id] * 3
    assert all(o.instruction_refreshed for o in outcomes)
    done = _round(engine, row.id)
    assert (done.status, done.produced) == (RoundStatus.DONE, 1)
    assert (done.lessons_applied, done.lessons_error) == (3, None)

    # Already learned: the next run has nothing to do.
    again = apply_pending_lessons(session, round_id=99, profile=PYTHON_PROFILE)
    assert (again.applied, refreshes.calls) == (0, [MC])


def test_each_judge_relearns_once_however_many_reviews_named_it(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    judge_calls: list[JudgeMetricId] = []
    monkeypatch.setattr(
        "app.feedback.lessons.refresh_judge_prompt",
        lambda _session, metric, **_kw: judge_calls.append(metric) or object(),
    )
    monkeypatch.setattr("app.feedback.lessons.distill_guidelines", TypeRefreshes())
    for _ in range(2):
        question = _question(session, gate=JudgeGate.APPROVED)
        review = submit_review(
            session,
            question_id=question.id,
            decision=ReviewDecision.REJECT,
            reasons=[RejectionReason.TOO_EASY],
        )
        assert route_review_outcome(session, review).cell is QuadrantCell.MISSED
        session.commit()

    run = apply_pending_lessons(session, round_id=1, profile=PYTHON_PROFILE)

    assert judge_calls == [JudgeMetricId.DIFFICULTY]
    assert run.applied == 2
    assert all(o.judges_refreshed == [JudgeMetricId.DIFFICULTY] for o in _all_outcomes(session))


def _all_outcomes(session: Session) -> list[ReviewOutcomeRow]:
    session.expire_all()
    return ReviewOutcomeRepository(session).list_recent()


def test_a_failing_refresh_does_not_fail_the_round(
    session: Session, engine: Engine, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.feedback.lessons.distill_guidelines", TypeRefreshes(fail=True))
    _reject(session, _question(session, gate=JudgeGate.REJECT, version_id=env.version.id))

    setup = _setup(session, env, [(env.while_loops.id, "medium", 1)])
    row = _queue(session, setup, [_target(env)])
    _run(engine, row.id, _round_client(env))

    done = _round(engine, row.id)
    assert (done.status, done.produced) == (RoundStatus.DONE, 1)
    assert done.lessons_applied == 0
    assert "provider" in (done.lessons_error or "").lower()
    (outcome,) = _outcomes(engine)
    assert "provider" in (outcome.refresh_error or "").lower()
    assert outcome.instruction_refreshed is False
    # Not learned, so the next round tries again.
    assert outcome.lessons_round_id is None


def test_an_unexpected_error_in_the_lesson_run_does_not_fail_the_round(
    session: Session, engine: Engine, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: Any, **_kwargs: Any):
        raise RuntimeError("bug")

    monkeypatch.setattr("app.generation.rounds.apply_pending_lessons", broken)
    setup = _setup(session, env, [(env.while_loops.id, "medium", 1)])
    row = _queue(session, setup, [_target(env)])
    _run(engine, row.id, _round_client(env))

    done = _round(engine, row.id)
    assert (done.status, done.produced) == (RoundStatus.DONE, 1)
    assert done.lessons_error == "Lessons were not applied (RuntimeError)."


def test_another_subjects_reviews_wait_for_their_own_round(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    refreshes = TypeRefreshes()
    monkeypatch.setattr("app.feedback.lessons.distill_guidelines", refreshes)
    course = CourseRow(name="Physics course", subject="physics")
    session.add(course)
    session.flush()
    version = CurriculumVersionRow(course_id=course.id, label="Physics taxonomy")
    session.add(version)
    session.commit()
    _reject(session, _question(session, gate=JudgeGate.REJECT, version_id=version.id))

    run = apply_pending_lessons(session, round_id=1, profile=PYTHON_PROFILE)

    assert (run.applied, refreshes.calls) == (0, [])
    (outcome,) = _all_outcomes(session)
    assert outcome.lessons_round_id is None


def test_frozen_learning_consumes_the_reviews_without_learning(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JUDGE_LEARNING_ENABLED", "false")
    monkeypatch.setenv("GENERATOR_LEARNING_ENABLED", "false")
    get_settings.cache_clear()
    refreshes = TypeRefreshes()
    monkeypatch.setattr("app.feedback.lessons.distill_guidelines", refreshes)
    _reject(session, _question(session, gate=JudgeGate.APPROVED))

    run = apply_pending_lessons(session, round_id=1, profile=PYTHON_PROFILE)

    assert (run.applied, refreshes.calls) == (1, [])


def test_the_round_api_reports_the_lessons(session: Session, env: SimpleNamespace) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "medium", 1)])
    row = _queue(session, setup, [_target(env)])
    row.lessons_applied = 4
    row.lessons_error = "multiple_choice: The provider is unavailable."

    out = GenerationRoundOut.from_row(row)

    assert (out.lessons_applied, out.lessons_error) == (4, row.lessons_error)
