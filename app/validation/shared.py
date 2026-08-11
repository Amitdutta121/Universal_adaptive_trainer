"""Deterministic grounding checks shared by every question type."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus
from app.domain.questions import Question, QuestionCheck
from app.errors import NotFoundError
from app.persistence.repositories import BookStructureRepository, CurriculumRepository
from app.validation.report import make_check


def _source_section_ids(question: Question) -> set[int]:
    """Collect integer section ids from the frozen request and generated content."""
    section_ids: set[int] = set()
    if question.spec is not None:
        source_section_ids = question.spec.get("source_section_ids")
        if isinstance(source_section_ids, list):
            section_ids.update(value for value in source_section_ids if type(value) is int)

    if question.content is not None:
        sources = question.content.get("sources")
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, dict) and type(source.get("section_id")) is int:
                    section_ids.add(source["section_id"])
    return section_ids


def _has_approved_taxonomy_ids(question: Question, session: Session | None) -> bool:
    """Return whether the question's ids name a pair in its approved curriculum."""
    if session is None or question.curriculum_version_id is None:
        return False
    try:
        version = CurriculumRepository(session).get_with_tree(question.curriculum_version_id)
    except NotFoundError:
        return False
    if version.status != CurriculumStatus.APPROVED:
        return False
    return any(
        topic.id == question.topic_id
        and any(subtopic.id == question.subtopic_id for subtopic in topic.subtopics)
        for topic in version.topics
    )


def _has_existing_source_sections(question: Question, session: Session | None) -> bool:
    """Return whether every declared source section exists."""
    section_ids = _source_section_ids(question)
    if session is None or not section_ids:
        return False
    repository = BookStructureRepository(session)
    try:
        for section_id in section_ids:
            repository.get_section(section_id)
    except NotFoundError:
        return False
    return True


def check_shared(question: Question, session: Session | None) -> list[QuestionCheck]:
    """Check required curriculum, source, type, and difficulty grounding."""
    taxonomy_ids_valid = _has_approved_taxonomy_ids(question, session)
    source_sections_valid = _has_existing_source_sections(question, session)
    question_type_valid = question.question_type is not None

    return [
        make_check(
            "approved_taxonomy_ids",
            taxonomy_ids_valid,
            (
                "Approved curriculum IDs"
                if taxonomy_ids_valid
                else "Curriculum IDs are not an approved topic/subtopic pair."
            ),
        ),
        make_check(
            "source_section_ids",
            source_sections_valid,
            (
                "Source section IDs exist"
                if source_sections_valid
                else "Source section IDs are missing or do not exist."
            ),
        ),
        make_check(
            "allowed_question_type",
            question_type_valid,
            "Allowed question type" if question_type_valid else "Question type is not allowed.",
        ),
        make_check("allowed_difficulty", True, "Allowed difficulty"),
    ]
