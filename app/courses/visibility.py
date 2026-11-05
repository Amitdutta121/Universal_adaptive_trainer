"""Hide approved questions from students, and show them again (ADR-070, task-139).

Turning a style or a question type off stops new questions in it; the professor may also hide
the approved questions already written in it. Hidden is its own status
(:attr:`QuestionStatus.HIDDEN`): every serving path reads ``APPROVED`` only, so a hidden question
is never served, and ``style_rejects`` reads ``REJECTED`` only, so it is never a reject.

Scope is the whole course (every question of the course with that style or type) or one
subtopic (questions *tagged* with it, as serving and coverage read them). Status is per
question, so hiding a question tagged with two subtopics hides it in both.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionStatus, QuestionType
from app.errors import DomainRuleError
from app.persistence.models import QuestionRow, QuestionSubtopicRow
from app.persistence.repositories import questions_in_course

_VISIBLE_OR_HIDDEN = (QuestionStatus.APPROVED, QuestionStatus.HIDDEN)


@dataclass
class Tally:
    approved: int = 0
    hidden: int = 0

    def add(self, status: QuestionStatus, count: int) -> None:
        if status is QuestionStatus.APPROVED:
            self.approved += count
        else:
            self.hidden += count


@dataclass
class VisibilityCounts:
    by_style: dict[str, Tally] = field(default_factory=dict)
    by_type: dict[QuestionType, Tally] = field(default_factory=dict)
    #: ``(subtopic_id, style_id or None, difficulty)``; only for the taxonomy asked about.
    by_cell: dict[tuple[int, str | None, Difficulty], Tally] = field(default_factory=dict)


def visibility_counts(
    session: Session, course_id: int, *, curriculum_version_id: int | None = None
) -> VisibilityCounts:
    """Approved and hidden questions of a course, per style and per type; per subtopic,
    style and difficulty for one taxonomy when ``curriculum_version_id`` is given."""
    counts = VisibilityCounts()
    in_course = (questions_in_course(course_id), QuestionRow.status.in_(_VISIBLE_OR_HIDDEN))

    by_style = (
        select(QuestionRow.style_id, QuestionRow.status, func.count())
        .where(*in_course, QuestionRow.style_id.is_not(None))
        .group_by(QuestionRow.style_id, QuestionRow.status)
    )
    for style_id, status, count in session.execute(by_style):
        counts.by_style.setdefault(style_id, Tally()).add(status, count)

    by_type = (
        select(QuestionRow.question_type, QuestionRow.status, func.count())
        .where(*in_course, QuestionRow.question_type.is_not(None))
        .group_by(QuestionRow.question_type, QuestionRow.status)
    )
    for question_type, status, count in session.execute(by_type):
        counts.by_type.setdefault(question_type, Tally()).add(status, count)

    if curriculum_version_id is not None:
        by_cell = (
            select(
                QuestionSubtopicRow.subtopic_id,
                QuestionRow.style_id,
                QuestionRow.difficulty,
                QuestionRow.status,
                func.count(func.distinct(QuestionRow.id)),
            )
            .join(QuestionRow, QuestionRow.id == QuestionSubtopicRow.question_id)
            .where(*in_course, QuestionRow.curriculum_version_id == curriculum_version_id)
            .group_by(
                QuestionSubtopicRow.subtopic_id,
                QuestionRow.style_id,
                QuestionRow.difficulty,
                QuestionRow.status,
            )
        )
        for subtopic_id, style_id, difficulty, status, count in session.execute(by_cell):
            key = (subtopic_id, style_id, Difficulty(difficulty))
            counts.by_cell.setdefault(key, Tally()).add(status, count)
    return counts


def set_hidden(
    session: Session,
    course_id: int,
    *,
    hidden: bool,
    style_ids: Collection[str] = (),
    question_types: Collection[QuestionType] = (),
    subtopic_id: int | None = None,
) -> int:
    """Hide the course's approved questions in these styles or types (or show hidden ones
    again), course-wide or in one subtopic. Returns how many changed. Does not commit."""
    if bool(style_ids) == bool(question_types):
        raise DomainRuleError("Name either styles or question types to hide or show.")
    source, target = (
        (QuestionStatus.APPROVED, QuestionStatus.HIDDEN)
        if hidden
        else (QuestionStatus.HIDDEN, QuestionStatus.APPROVED)
    )
    stmt = select(QuestionRow).where(questions_in_course(course_id), QuestionRow.status == source)
    if style_ids:
        stmt = stmt.where(QuestionRow.style_id.in_(list(style_ids)))
    else:
        stmt = stmt.where(QuestionRow.question_type.in_(list(question_types)))
    if subtopic_id is not None:
        tagged = select(QuestionSubtopicRow.question_id).where(
            QuestionSubtopicRow.subtopic_id == subtopic_id
        )
        stmt = stmt.where(QuestionRow.id.in_(tagged))
    rows = list(session.scalars(stmt))
    for row in rows:
        row.status = target
    session.flush()
    return len(rows)
