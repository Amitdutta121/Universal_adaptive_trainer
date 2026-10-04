"""Live classroom stock, approval isolation and asynchronous refill integration."""

from concurrent.futures import ThreadPoolExecutor

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_adaptive_service import _bank, _true_false
from test_rounds import STYLE_A

from app.adaptive.inventory import StudentBank
from app.adaptive.service import AdaptiveTrainingEngine
from app.domain.enums import Difficulty, QuestionStatus, RoundStatus
from app.generation import refill, rounds
from app.persistence.models import GenerationRoundRow, QuestionSetupRow
from app.persistence.repositories import QuestionSetRepository
from app.web.routes.api import students


def _live(session, monkeypatch, *, questions=1):
    bank = _bank(session, questions=questions)
    snapshot = QuestionSetRepository(session).get(bank.set_id)
    snapshot.notes = "Behind this taxonomy's classroom link"
    setup = QuestionSetupRow(
        curriculum_version_id=bank.version.id,
        approved_styles={str(bank.subtopic_ids[0]): [STYLE_A.id]},
        cell_targets=[{"subtopic_id": bank.subtopic_ids[0], "difficulty": "easy", "target": 1}],
    )
    session.add(setup)
    session.commit()
    monkeypatch.setattr(rounds, "get_library", lambda subject: [STYLE_A])
    return bank, setup


def _add(session, bank, status=QuestionStatus.APPROVED):
    question = _true_false(
        session, version=bank.version, topic_id=bank.topic_id, subtopic_ids=bank.subtopic_ids
    )
    question.status = status
    session.commit()
    return question


def test_live_additions_and_frozen_membership_are_distinct(session, monkeypatch):
    bank, _ = _live(session, monkeypatch)
    snapshot = QuestionSetRepository(session).get(bank.set_id)
    original = {m.question_id for m in snapshot.members}
    approved = _add(session, bank)
    pending = _add(session, bank, QuestionStatus.VALIDATION_PASSED)
    pending.trust_provenance = "audit"
    session.commit()
    rejected = _add(session, bank, QuestionStatus.REJECTED)
    assert {q.id for q in StudentBank(session).questions(bank.set_id)} == original | {approved.id}
    assert pending.id not in original and rejected.id not in original
    assert {m.question_id for m in snapshot.members} == original
    assert snapshot.question_count == 1
    snapshot.notes = None
    session.commit()
    assert {q.id for q in StudentBank(session).questions(bank.set_id)} == original
    assert refill.plan_refill(session, bank.run.id) is None


def test_unseen_stock_refills_beyond_full_professor_coverage(session, monkeypatch):
    bank, setup = _live(session, monkeypatch, questions=3)
    assert refill.plan_refill(session, bank.run.id) is None
    engine = AdaptiveTrainingEngine(session)
    for _ in range(2):
        served = engine.serve_next(bank.run.id)
        engine.submit_answer(served.attempt.id, "false")
        session.commit()
    plan = refill.plan_refill(session, bank.run.id)
    assert plan.deficits == {(bank.subtopic_ids[0], Difficulty.EASY): 2}
    assert rounds.plan_targets(session, setup, size=10) == []
    row = rounds.refill_round(session, setup.id, plan.deficits)
    assert row.requested == 2
    assert all(t["subtopic_id"] == bank.subtopic_ids[0] for t in row.targets)
    assert refill.plan_refill(session, bank.run.id) is None
    assert rounds.refill_round(session, setup.id, plan.deficits) is None


def test_older_setup_active_round_suppresses_refill(session, monkeypatch):
    bank, setup = _live(session, monkeypatch)
    row = rounds.refill_round(
        session, setup.id, {(bank.subtopic_ids[0], Difficulty.EASY): 30}, size=99
    )
    assert row.requested == 10
    session.add(
        QuestionSetupRow(
            curriculum_version_id=bank.version.id,
            approved_styles=setup.approved_styles,
            cell_targets=setup.cell_targets,
        )
    )
    session.commit()
    assert refill.plan_refill(session, bank.run.id) is None


def test_background_owns_session_and_new_approval_is_live(session, engine, monkeypatch):
    bank, _ = _live(session, monkeypatch)
    pending = _add(session, bank, QuestionStatus.VALIDATION_PASSED)
    session.commit()
    sessions = []
    executed = []

    def factory():
        db = Session(engine)
        sessions.append(db)
        return db

    def finish(round_id, **kwargs):
        executed.append(round_id)
        with factory() as db:
            db.get(type(pending), pending.id).status = QuestionStatus.APPROVED
            db.get(GenerationRoundRow, round_id).status = RoundStatus.DONE
            db.commit()

    monkeypatch.setattr(refill, "run_round", finish)
    refill.schedule_refill(bank.run.id, session_factory=factory)
    assert executed and all(db is not session for db in sessions)
    session.expire_all()
    assert pending.id in {q.id for q in StudentBank(session).questions(bank.set_id)}
    assert QuestionSetRepository(session).get(bank.set_id).question_count == 1


def test_route_schedules_without_running_generator(session, monkeypatch):
    bank, _ = _live(session, monkeypatch)
    tasks = BackgroundTasks()
    served = students.next_question(session, bank.run.id, tasks)
    assert served is not None
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].func is refill.schedule_refill


def test_depleted_response_keeps_background_refill(session, monkeypatch):
    bank, _ = _live(session, monkeypatch, questions=0)
    tasks = BackgroundTasks()
    response = students.next_question(session, bank.run.id, tasks)
    assert response.status_code == 409
    assert response.background is tasks
    assert len(tasks.tasks) == 1
    assert list(session.scalars(select(GenerationRoundRow))) == []


def test_outstanding_question_withdrawal_never_exposes_unapproved(session, monkeypatch):
    import pytest

    from app.errors import NoQuestionAvailableError

    bank, _ = _live(session, monkeypatch)
    served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)
    served.question.status = QuestionStatus.VALIDATION_PASSED
    served.question.trust_provenance = "audit"
    session.commit()
    with pytest.raises(NoQuestionAvailableError):
        AdaptiveTrainingEngine(session).serve_next(bank.run.id)


def test_stock_policy_targets_only_scarce_cells():
    a, b = (1, Difficulty.EASY), (2, Difficulty.HARD)
    assert refill.inventory_deficits([a, b], {a: 1, b: 3}) == {a: 2}


def test_pending_audits_reserve_refill_capacity_until_rejected(session, monkeypatch):
    bank, _ = _live(session, monkeypatch, questions=0)
    pending = [_add(session, bank, QuestionStatus.VALIDATION_PASSED) for _ in range(3)]
    pending[0].trust_provenance = "audit"
    session.commit()
    assert StudentBank(session).questions(bank.set_id) == []
    for _ in range(2):
        tasks = BackgroundTasks()
        response = students.next_question(session, bank.run.id, tasks)
        assert response.status_code == 409
        assert not tasks.tasks
    assert list(session.scalars(select(GenerationRoundRow))) == []
    pending[0].status = QuestionStatus.REJECTED
    session.commit()
    plan = refill.plan_refill(session, bank.run.id)
    assert plan.deficits == {(bank.subtopic_ids[0], Difficulty.EASY): 1}


def test_concurrent_background_planners_create_one_active_round(session, engine, monkeypatch):
    bank, _ = _live(session, monkeypatch)
    session.commit()
    executed = []
    monkeypatch.setattr(refill, "run_round", lambda round_id, **kwargs: executed.append(round_id))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                refill.schedule_refill, bank.run.id, session_factory=lambda: Session(engine)
            )
            for _ in range(2)
        ]
        for future in futures:
            future.result(timeout=30)
    assert len(executed) == 1
    session.expire_all()
    rows = list(session.scalars(select(GenerationRoundRow)))
    assert len(rows) == 1 and rows[0].status == RoundStatus.QUEUED
