"""Building the coverage grid, and freezing an approved set (ADR-036).

The grid is walked from the taxonomy outwards. Starting from the questions and
grouping them would produce a report in which a subtopic nobody has written a
question for simply does not appear -- which is the one row the professor most
needs to see.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.coverage.schema import (
    MIN_QUESTIONS_PER_CELL,
    CoverageCell,
    CoverageReport,
    SubtopicCoverage,
    TopicCoverage,
    needed_for,
    state_for,
)
from app.domain.enums import Difficulty
from app.errors import DomainRuleError
from app.persistence.models import QuestionSetVersionRow
from app.persistence.repositories import CurriculumRepository, QuestionSetRepository

logger = logging.getLogger(__name__)


def build_coverage_report(
    session: Session,
    *,
    set_version_id: int | None = None,
    minimum_per_cell: int = MIN_QUESTIONS_PER_CELL,
) -> CoverageReport:
    """The subtopic x difficulty grid over approved questions.

    Without ``set_version_id`` this describes the live bank, which is what the
    professor reads while deciding what to generate next. With one it describes
    that frozen set, which is what a training run would actually serve.
    """
    sets = QuestionSetRepository(session)
    question_ids: list[int] | None = None
    curriculum_version_id: int | None = None

    if set_version_id is not None:
        set_version = sets.get(set_version_id)
        question_ids = [member.question_id for member in set_version.members]
        curriculum_version_id = set_version.curriculum_version_id

    curriculum = CurriculumRepository(session)
    version = (
        curriculum.get_with_tree(curriculum_version_id)
        if curriculum_version_id is not None
        else curriculum.get_approved()
    )
    if version is None:
        # No approved taxonomy is its own kind of not-ready. An empty grid would
        # read as "no subtopics need questions", which is the opposite.
        logger.info("No approved curriculum, so there is no grid to walk.")
        return CoverageReport(
            curriculum_version_id=None,
            curriculum_label=None,
            set_version_id=set_version_id,
            minimum_per_cell=minimum_per_cell,
        )

    if set_version_id is None:
        question_ids = sets.approved_question_ids(curriculum_version_id=version.id)

    counts = sets.coverage_counts(question_ids=question_ids)
    per_topic = sets.approved_question_counts_by_topic(question_ids=question_ids)

    def _cells(subtopic_id: int) -> list[CoverageCell]:
        cells = []
        for difficulty in Difficulty:
            count = counts.get((subtopic_id, difficulty), 0)
            cells.append(
                CoverageCell(
                    difficulty=difficulty,
                    count=count,
                    state=state_for(count, minimum=minimum_per_cell),
                    needed=needed_for(count, minimum=minimum_per_cell),
                )
            )
        return cells

    topics = [
        TopicCoverage(
            topic_id=topic.id,
            topic_name=topic.name,
            approved_questions=per_topic.get(topic.id, 0),
            subtopics=[
                SubtopicCoverage(
                    subtopic_id=subtopic.id,
                    subtopic_name=subtopic.name,
                    topic_id=topic.id,
                    topic_name=topic.name,
                    cells=_cells(subtopic.id),
                )
                for subtopic in sorted(topic.subtopics, key=lambda row: (row.position, row.id))
            ],
        )
        for topic in sorted(version.topics, key=lambda row: (row.position, row.id))
    ]

    return CoverageReport(
        curriculum_version_id=version.id,
        curriculum_label=version.label,
        set_version_id=set_version_id,
        minimum_per_cell=minimum_per_cell,
        topics=topics,
        question_count=len(question_ids or []),
    )


def create_question_set(
    session: Session, *, label: str, notes: str | None = None
) -> QuestionSetVersionRow:
    """Freeze every currently approved question as a new set.

    Refuses an empty set. A set with no questions cannot serve a student, and
    creating one would leave a named, dated, permanently useless row that later
    reads as a real snapshot of an empty moment.

    Raises:
        DomainRuleError: if no curriculum is approved, or nothing is approved.
    """
    clean = label.strip()
    if not clean:
        raise DomainRuleError("A question set needs a label.")

    version = CurriculumRepository(session).get_approved()
    if version is None:
        raise DomainRuleError("Approve a curriculum before freezing a question set.")

    sets = QuestionSetRepository(session)
    question_ids = sets.approved_question_ids(curriculum_version_id=version.id)
    if not question_ids:
        raise DomainRuleError("No approved question exists yet, so there is nothing to freeze.")

    row = sets.create(
        label=clean,
        question_ids=question_ids,
        curriculum_version_id=version.id,
        notes=notes,
    )
    session.commit()
    logger.info("Froze question set %s (%s) with %s questions.", row.id, clean, len(question_ids))
    return row
