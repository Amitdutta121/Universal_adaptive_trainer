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
    course_id: int | None = None,
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
        else curriculum.get_approved(course_id=course_id)
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
    session: Session,
    *,
    label: str,
    notes: str | None = None,
    course_id: int | None = None,
    curriculum_version_id: int | None = None,
) -> QuestionSetVersionRow:
    """Freeze every approved question of one taxonomy as a new set.

    ``curriculum_version_id`` names the taxonomy; without it, the course's selected
    taxonomy is used.

    Refuses an empty set. A set with no questions cannot serve a student, and
    creating one would leave a named, dated, permanently useless row that later
    reads as a real snapshot of an empty moment.

    Raises:
        DomainRuleError: if no curriculum is approved, or nothing is approved.
    """
    clean = label.strip()
    if not clean:
        raise DomainRuleError("A question set needs a label.")

    curriculum = CurriculumRepository(session)
    version = (
        curriculum.get_version(curriculum_version_id)
        if curriculum_version_id is not None
        else curriculum.get_approved(course_id=course_id)
    )
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


def sync_prod_question_set(
    session: Session, *, course_id: int | None = None
) -> QuestionSetVersionRow:
    """Create the next immutable prod snapshot and repoint the stable prod alias to it.

    There is still one ``prod`` alias for the whole installation: syncing from a
    course points it at that course's bank.
    """
    row = create_question_set(
        session,
        label="Prod classroom",
        notes="Current production classroom",
        course_id=course_id,
    )
    QuestionSetRepository(session).point_alias("prod", set_version_id=row.id)
    session.commit()
    logger.info("Synced prod classroom to question set %s.", row.id)
    return row


def taxonomy_alias(curriculum_version_id: int) -> str:
    """The stable name a taxonomy's classroom link resolves through."""
    return f"taxonomy-{curriculum_version_id}"


def sync_taxonomy_question_set(
    session: Session, curriculum_version_id: int
) -> QuestionSetVersionRow:
    """Freeze this taxonomy's approved questions and point its classroom link at them.

    Every taxonomy has its own link, so several taxonomies can be taught at once;
    the link never changes, only the snapshot behind it. Students already in a run
    keep the snapshot they started on (ADR-036).
    """
    version = CurriculumRepository(session).get_version(curriculum_version_id)
    row = create_question_set(
        session,
        label=f"{version.label} classroom",
        notes="Behind this taxonomy's classroom link",
        curriculum_version_id=curriculum_version_id,
    )
    QuestionSetRepository(session).point_alias(
        taxonomy_alias(curriculum_version_id), set_version_id=row.id
    )
    session.commit()
    logger.info("Synced taxonomy %s classroom to question set %s.", curriculum_version_id, row.id)
    return row


def get_taxonomy_question_set(
    session: Session, curriculum_version_id: int
) -> QuestionSetVersionRow:
    """The snapshot behind a taxonomy's classroom link.

    Raises:
        NotFoundError: the link has not been created for this taxonomy yet.
    """
    return QuestionSetRepository(session).resolve_alias(taxonomy_alias(curriculum_version_id))


def get_prod_question_set(session: Session) -> QuestionSetVersionRow:
    """Resolve the stable prod classroom alias to its current frozen snapshot."""
    return QuestionSetRepository(session).resolve_alias("prod")
