"""Validate generation requests against approved curriculum and book sections.

A :class:`QuestionSpec` is the stable contract shared by base, personalized and
future generators. :func:`build_question_spec` resolves database ids and rejects
foreign or missing references before any LLM call.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus, Difficulty, QuestionType
from app.errors import InvalidQuestionSpecError, NotFoundError
from app.persistence.repositories import BookStructureRepository, CurriculumRepository


class QuestionSpec(BaseModel):
    """Resolved generation request with validated curriculum and section ids."""

    curriculum_version_id: int
    topic_id: int
    subtopic_ids: list[int] = Field(min_length=1)
    question_type: QuestionType
    difficulty: Difficulty
    source_section_ids: list[int] = Field(min_length=1, max_length=1)
    seed: str | None = None


def build_question_spec(
    session: Session,
    *,
    curriculum_version_id: int,
    topic_id: int,
    subtopic_ids: list[int],
    question_type: QuestionType,
    difficulty: Difficulty,
    source_section_ids: list[int],
    seed: str | None = None,
) -> QuestionSpec:
    """Resolve and validate ids for one generation request.

    Raises:
        InvalidQuestionSpecError: the curriculum is not approved, or any id is
            missing or does not belong to the requested taxonomy tree.
    """
    curriculum = CurriculumRepository(session)
    structure = BookStructureRepository(session)

    version = curriculum.get_with_tree(curriculum_version_id)
    status = CurriculumStatus(version.status)
    if status is not CurriculumStatus.APPROVED:
        raise InvalidQuestionSpecError(
            "Question generation requires an approved curriculum version.",
            detail=f"Version {curriculum_version_id} has status {status.value}.",
        )

    topic = next((row for row in version.topics if row.id == topic_id), None)
    if topic is None:
        raise InvalidQuestionSpecError(
            "Topic is not part of the requested curriculum version.",
            detail=f"Topic {topic_id} is not in approved version {curriculum_version_id}.",
        )

    topic_subtopic_ids = {row.id for row in topic.subtopics}
    foreign_subtopics = [sid for sid in subtopic_ids if sid not in topic_subtopic_ids]
    if foreign_subtopics:
        raise InvalidQuestionSpecError(
            "Every subtopic must belong to the requested topic.",
            detail=f"Subtopic id(s) not under topic {topic_id}: {foreign_subtopics}",
        )

    for section_id in source_section_ids:
        try:
            structure.get_section(section_id)
        except NotFoundError:
            raise InvalidQuestionSpecError(
                "Every source section must exist.",
                detail=f"Section {section_id} does not exist.",
            ) from None

    try:
        return QuestionSpec(
            curriculum_version_id=curriculum_version_id,
            topic_id=topic_id,
            subtopic_ids=subtopic_ids,
            question_type=question_type,
            difficulty=difficulty,
            source_section_ids=source_section_ids,
            seed=seed,
        )
    except ValidationError as exc:
        raise InvalidQuestionSpecError(
            "A cold-start question spec needs exactly one source section.",
            detail=str(exc.errors()),
        ) from None
