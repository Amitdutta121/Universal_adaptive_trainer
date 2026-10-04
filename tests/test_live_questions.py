"""Live questions: generated on demand when a student has nothing new to answer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import BackgroundTasks
from llm_fakes import MetricJudgeClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_live_refill import _live
from test_rounds import (  # noqa: F401 -- fixtures
    STYLE_A,
    KeywordEmbedder,
    _mcq,
    _setup,
    env,
    fake_library,
)

from app.adaptive.inventory import StudentBank
from app.adaptive.service import AdaptiveTrainingEngine
from app.domain.enums import Difficulty, QuestionStatus, QuestionType, RoundStatus
from app.errors import NoQuestionAvailableError
from app.generation import live
from app.persistence.models import LiveQuestionJobRow, QuestionRow, QuestionSetupRow
from app.persistence.repositories import (
    QuestionSetRepository,
    StudentRepository,
    TrainingSessionRepository,
)
from app.web.routes.api import students


@pytest.fixture(autouse=True)
def live_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live, "_llm_ready", lambda: True)
    monkeypatch.setattr(live, "get_library", lambda subject: [STYLE_A])


def _answer_everything(session: Session, run_id: int) -> None:
    engine = AdaptiveTrainingEngine(session)
    while True:
        served = engine.serve_next(run_id)
        if served.question.id in engine._attempts.answered_question_ids(served.attempt.student_id):
            session.rollback()
            return
        engine.submit_answer(served.attempt.id, "true")
        session.commit()


def _finish(session: Session, job: LiveQuestionJobRow, status=QuestionStatus.VALIDATION_PASSED):
    """What a successful ``run_live_job`` leaves behind, without a model."""
    question = QuestionRow(
        prompt="Fresh?",
        curriculum_version_id=session.get(QuestionSetupRow, job.setup_id).curriculum_version_id,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=job.difficulty,
        status=status,
        style_id=job.style_id,
        target_subtopic_id=job.subtopic_id,
        subtopic_ids=[job.subtopic_id],
        live_generated=True,
        content={"prompt": "Fresh?", "correct_answer": True, "explanation": "Yes."},
    )
    session.add(question)
    session.flush()
    job.status, job.question_id = RoundStatus.DONE, question.id
    job.finished_at = datetime.now(UTC)
    session.commit()
    return question


def test_a_repeat_starts_one_live_job_for_the_drawn_cell(session, monkeypatch):
    bank, setup = _live(session, monkeypatch)
    _answer_everything(session, bank.run.id)

    job = live.next_for_session(session, bank.run.id)
    session.commit()

    assert isinstance(job, LiveQuestionJobRow)
    assert (job.status, job.setup_id, job.subtopic_id, job.style_id) == (
        RoundStatus.QUEUED,
        setup.id,
        bank.subtopic_ids[0],
        STYLE_A.id,
    )
    assert job.requested_difficulty is Difficulty.EASY
    assert live.next_for_session(session, bank.run.id).id == job.id
    assert len(list(session.scalars(select(LiveQuestionJobRow)))) == 1


def test_an_empty_bank_generates_for_the_students_current_topic(session, monkeypatch):
    bank, _ = _live(session, monkeypatch, questions=0)

    job = live.next_for_session(session, bank.run.id)

    assert isinstance(job, LiveQuestionJobRow)
    assert job.subtopic_id == bank.subtopic_ids[0]


def test_a_finished_job_is_served_once_even_before_approval(session, monkeypatch):
    bank, _ = _live(session, monkeypatch)
    _answer_everything(session, bank.run.id)
    job = live.next_for_session(session, bank.run.id)
    question = _finish(session, job)

    served = live.next_for_session(session, bank.run.id)
    session.commit()

    assert served.question.id == question.id and served.live and not served.resumed
    assert job.attempt_id == served.attempt.id
    # Not approved: nobody else's bank has it.
    assert question.id not in {q.id for q in StudentBank(session).questions(bank.set_id)}
    # A reload resumes it rather than refusing an unapproved question.
    again = live.next_for_session(session, bank.run.id)
    assert again.resumed and again.live and again.attempt.id == served.attempt.id
    result = AdaptiveTrainingEngine(session).submit_answer(served.attempt.id, "true")
    assert result.scored.score == 100


def test_a_reject_before_serving_withdraws_the_question(session, monkeypatch):
    bank, _ = _live(session, monkeypatch, questions=0)
    job = live.next_for_session(session, bank.run.id)
    _finish(session, job, status=QuestionStatus.REJECTED)

    with pytest.raises(NoQuestionAvailableError) as raised:
        live.next_for_session(session, bank.run.id)

    assert job.status is RoundStatus.FAILED and "withdrew" in job.error
    assert raised.value.detail == job.error


def test_a_reject_after_serving_withdraws_the_outstanding_question(session, monkeypatch):
    bank, _ = _live(session, monkeypatch, questions=0)
    job = live.next_for_session(session, bank.run.id)
    question = _finish(session, job)
    live.next_for_session(session, bank.run.id)
    question.status = QuestionStatus.REJECTED
    session.commit()

    with pytest.raises(NoQuestionAvailableError):
        live.next_for_session(session, bank.run.id)


def test_a_failure_falls_back_to_the_bank_until_the_student_retries(session, monkeypatch):
    bank, _ = _live(session, monkeypatch)
    _answer_everything(session, bank.run.id)
    job = live.next_for_session(session, bank.run.id)
    job.status, job.error = RoundStatus.FAILED, "None of the drafts passed."
    job.finished_at = datetime.now(UTC)
    session.commit()

    repeat = live.next_for_session(session, bank.run.id)
    (only,) = StudentBank(session).questions(bank.set_id)
    assert not repeat.live and repeat.question.id == only.id
    AdaptiveTrainingEngine(session).submit_answer(repeat.attempt.id, "true")
    session.commit()

    retried = live.next_for_session(session, bank.run.id, force=True)
    assert isinstance(retried, LiveQuestionJobRow) and retried.id != job.id


def test_a_job_whose_worker_died_expires(session, monkeypatch):
    bank, _ = _live(session, monkeypatch, questions=0)
    job = live.next_for_session(session, bank.run.id)
    job.created_at = datetime.now(UTC) - live.LIVE_JOB_TIMEOUT - timedelta(seconds=1)
    session.commit()

    with pytest.raises(NoQuestionAvailableError):
        live.next_for_session(session, bank.run.id)
    assert job.status is RoundStatus.FAILED


def test_an_ordinary_snapshot_never_generates(session, monkeypatch):
    bank, _ = _live(session, monkeypatch)
    QuestionSetRepository(session).get(bank.set_id).notes = None
    session.commit()
    _answer_everything(session, bank.run.id)

    served = live.next_for_session(session, bank.run.id)

    assert not isinstance(served, LiveQuestionJobRow) and not served.live
    assert list(session.scalars(select(LiveQuestionJobRow))) == []


def test_without_a_model_the_bank_behaves_as_before(session, monkeypatch):
    monkeypatch.setattr(live, "_llm_ready", lambda: False)
    bank, _ = _live(session, monkeypatch, questions=0)

    with pytest.raises(NoQuestionAvailableError):
        live.next_for_session(session, bank.run.id)


def test_the_route_reports_generating_and_schedules_the_job(session, monkeypatch):
    bank, _ = _live(session, monkeypatch, questions=0)
    tasks = BackgroundTasks()

    response = students.next_question(session, bank.run.id, tasks)

    assert response.status_code == 409
    assert b'"question_generating"' in response.body
    assert [task.func for task in tasks.tasks] == [live.run_live_job]


def test_the_route_serves_a_ready_live_question(session, monkeypatch):
    bank, _ = _live(session, monkeypatch, questions=0)
    job = live.next_for_session(session, bank.run.id)
    _finish(session, job)

    served = students.next_question(session, bank.run.id, BackgroundTasks())

    assert served.live is True and served.question_id == job.question_id


def test_run_live_job_uses_the_aligned_generator(
    session: Session,
    engine: Engine,
    env,  # noqa: F811
):
    _setup(
        session, env, [(env.while_loops.id, "easy", 1)], styles={env.while_loops.id: [STYLE_A.id]}
    )
    accepted = QuestionRow(
        curriculum_version_id=env.version.id,
        topic_id=env.while_loops.topic_id,
        subtopic_ids=[env.while_loops.id],
        question_type=QuestionType.TRUE_FALSE,
        difficulty=Difficulty.EASY,
        status=QuestionStatus.APPROVED,
        prompt="Accepted: what does a while loop do?",
        content={"prompt": "Loops?", "correct_answer": True, "explanation": "Yes."},
    )
    session.add(accepted)
    student = StudentRepository(session).add("Grace")
    classroom = QuestionSetRepository(session).create(
        label="Live", question_ids=[], curriculum_version_id=env.version.id
    )
    classroom.notes = "Behind this taxonomy's classroom link"
    run = TrainingSessionRepository(session).create(
        student_id=student.id, set_version_id=classroom.id, rng_seed=3
    )
    session.commit()
    _answer_everything(session, run.id)

    job = live.next_for_session(session, run.id)
    session.commit()
    assert isinstance(job, LiveQuestionJobRow)
    client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id), difficulty=job.difficulty
    )

    live.run_live_job(
        job.id,
        client=client,  # type: ignore[arg-type]
        embedder=KeywordEmbedder(),  # type: ignore[arg-type]
        session_factory=lambda: Session(engine, expire_on_commit=False),
    )

    session.expire_all()
    job = session.get(LiveQuestionJobRow, job.id)
    assert job.status is RoundStatus.DONE, job.error
    question = session.get(QuestionRow, job.question_id)
    assert question.live_generated and question.style_id == STYLE_A.id
    assert question.target_subtopic_id == env.while_loops.id
    assert question.trust_provenance is not None
    assert "Accepted: what does a while loop do?" in client.generation_calls[0]["prompt"]

    served = live.next_for_session(session, run.id)
    assert served.live and served.question.id == question.id

    # A repeated task is a no-op.
    live.run_live_job(
        job.id,
        client=client,  # type: ignore[arg-type]
        session_factory=lambda: Session(engine, expire_on_commit=False),
    )
    assert len(list(session.scalars(select(QuestionRow).where(QuestionRow.live_generated)))) == 1


def test_a_live_job_that_drops_every_draft_fails_with_a_reason(
    session: Session,
    engine: Engine,
    env,  # noqa: F811
    monkeypatch,
):
    _setup(
        session, env, [(env.while_loops.id, "easy", 1)], styles={env.while_loops.id: [STYLE_A.id]}
    )
    student = StudentRepository(session).add("Linus")
    classroom = QuestionSetRepository(session).create(
        label="Live", question_ids=[], curriculum_version_id=env.version.id
    )
    classroom.notes = "Behind this taxonomy's classroom link"
    run = TrainingSessionRepository(session).create(
        student_id=student.id, set_version_id=classroom.id, rng_seed=3
    )
    session.commit()
    job = live.next_for_session(session, run.id)
    session.commit()
    from app.generation.service import GenerationService

    monkeypatch.setattr(GenerationService, "generate_round_question", lambda *a, **k: None)

    live.run_live_job(
        job.id,
        client=object(),  # type: ignore[arg-type]
        embedder=KeywordEmbedder(),  # type: ignore[arg-type]
        session_factory=lambda: Session(engine, expire_on_commit=False),
    )

    session.expire_all()
    job = session.get(LiveQuestionJobRow, job.id)
    assert job.status is RoundStatus.FAILED
    assert job.error == "None of the drafts passed the professor's checks."
