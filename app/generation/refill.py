"""Background replenishment driven by unseen approved student inventory.

This loop never treats student answers as professor feedback. Planning is
read-only; generation uses the ordinary round service and its approval routing.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.adaptive.inventory import StudentBank, is_live_set
from app.domain.enums import Difficulty, QuestionStatus
from app.generation.rounds import Cell, _lock_taxonomy, active_round, refill_round, run_round
from app.persistence.models import QuestionRow, StudentAttemptRow
from app.persistence.repositories import (
    QuestionSetRepository,
    QuestionSetupRepository,
    TrainingSessionRepository,
)

logger = logging.getLogger(__name__)
LOW_STOCK = 1
UNSEEN_TARGET = 3


@dataclass(frozen=True)
class RefillPlan:
    setup_id: int
    deficits: dict[Cell, int]


def inventory_deficits(
    cells: list[Cell],
    counts: dict[Cell, int],
    *,
    low_stock: int = LOW_STOCK,
    target: int = UNSEEN_TARGET,
    reservations: dict[Cell, int] | None = None,
) -> dict[Cell, int]:
    """Pure low-stock policy; pending reviews reserve capacity, never eligibility."""
    reservations = reservations or {}
    return {
        cell: target - counts.get(cell, 0) - reservations.get(cell, 0)
        for cell in cells
        if counts.get(cell, 0) <= low_stock
        and counts.get(cell, 0) + reservations.get(cell, 0) < target
    }


def plan_refill(session: Session, training_session_id: int) -> RefillPlan | None:
    """Read-only planning: no model calls, writes, or answer correctness reads."""
    run = TrainingSessionRepository(session).get(training_session_id)
    if run.ended_at is not None or run.set_version_id is None:
        return None
    bank = QuestionSetRepository(session).get(run.set_version_id)
    if not is_live_set(bank):
        return None
    setup = QuestionSetupRepository(session).current(bank.curriculum_version_id)
    if setup is None or active_round(session, setup.curriculum_version_id) is not None:
        return None
    seen = set(
        session.scalars(
            select(StudentAttemptRow.question_id).where(
                StudentAttemptRow.student_id == run.student_id,
            )
        )
    )
    counts: Counter[Cell] = Counter()
    for question in StudentBank(session).questions(bank.id):
        if question.id not in seen:
            for sid in question.subtopic_ids:
                counts[(sid, Difficulty(question.difficulty))] += 1
    reservations: Counter[Cell] = Counter()
    pending = session.scalars(
        select(QuestionRow).where(
            QuestionRow.curriculum_version_id == bank.curriculum_version_id,
            QuestionRow.status.in_((QuestionStatus.GENERATED, QuestionStatus.VALIDATION_PASSED)),
        )
    )
    for question in pending:
        if question.id in seen:
            continue
        subtopics = set(question.subtopic_ids)
        if question.target_subtopic_id is not None:
            subtopics.add(question.target_subtopic_id)
        for sid in subtopics:
            reservations[(sid, Difficulty(question.difficulty))] += 1
    cells = [
        (int(entry["subtopic_id"]), Difficulty(entry["difficulty"]))
        for entry in setup.cell_targets or []
        if int(entry["target"]) > 0
    ]
    deficits = inventory_deficits(cells, counts, reservations=reservations)
    return RefillPlan(setup.id, deficits) if deficits else None


def schedule_refill(
    training_session_id: int,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Own the background session and recheck stock under the planning lock.

    SQLite serializes planners before their first read. Other engines lock the
    taxonomy row and replan after acquiring it. The round commits before execution.
    """
    if session_factory is None:
        from app.persistence.database import get_session_factory

        session_factory = get_session_factory()
    session = session_factory()
    round_id = None
    try:
        if session.get_bind().dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        plan = plan_refill(session, training_session_id)
        if plan is not None:
            setup = QuestionSetupRepository(session).get(plan.setup_id)
            _lock_taxonomy(session, setup.curriculum_version_id)
            plan = plan_refill(session, training_session_id)
        if plan is not None:
            row = refill_round(session, plan.setup_id, plan.deficits)
            if row is not None:
                round_id = row.id
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Could not plan refill for session %s", training_session_id)
    finally:
        session.close()
    if round_id is not None:
        run_round(round_id, session_factory=session_factory)
