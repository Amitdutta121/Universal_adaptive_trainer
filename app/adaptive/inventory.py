"""Approved eligibility for immutable snapshots and managed live classrooms.

Managed classroom snapshots already carry reserved notes from coverage.service.
Those notes persist when an alias moves, so existing classroom sessions keep their
live semantics. Ordinary snapshots never gain members. ``live-bank`` is an
additive opt-in for integrations creating sets directly.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionStatus
from app.persistence.models import QuestionRow, QuestionSetVersionRow
from app.persistence.repositories import QuestionSetRepository

LIVE_NOTES = frozenset(
    {
        "Current production classroom",
        "Behind this taxonomy's classroom link",
        "live-bank",
    }
)


def is_live_set(row: QuestionSetVersionRow) -> bool:
    return row.curriculum_version_id is not None and row.notes in LIVE_NOTES


class StudentBank:
    """Query only approved questions; pending audits have no serving eligibility."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sets = QuestionSetRepository(session)

    def questions(self, set_id: int) -> list[QuestionRow]:
        row = self.sets.get(set_id)
        stmt = select(QuestionRow).where(QuestionRow.status == QuestionStatus.APPROVED)
        if is_live_set(row):
            stmt = stmt.where(QuestionRow.curriculum_version_id == row.curriculum_version_id)
        else:
            stmt = stmt.where(QuestionRow.id.in_([member.question_id for member in row.members]))
        return list(self.session.scalars(stmt.order_by(QuestionRow.id)))

    def servable_subtopic_ids(self, set_id: int) -> set[int]:
        return {sid for question in self.questions(set_id) for sid in question.subtopic_ids}

    def candidates_for_cell(
        self, set_id: int, *, subtopic_id: int, difficulty: Difficulty
    ) -> list[tuple[int, int, int]]:
        return [
            (q.id, q.priority, q.times_used)
            for q in self.questions(set_id)
            if q.difficulty == difficulty and subtopic_id in q.subtopic_ids
        ]
