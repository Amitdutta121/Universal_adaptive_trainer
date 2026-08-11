"""Tests for deterministic shared question-grounding checks."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import CurriculumStatus, Difficulty, QuestionType
from app.domain.questions import Question
from app.ingestion import BookImportService
from app.persistence.repositories import CurriculumRepository
from app.validation.shared import check_shared


def _seed(session: Session, settings: Any) -> tuple[int, int, int, int]:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.think_python())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
        ),
    )
    session.commit()
    return (
        version.id,
        version.topics[0].id,
        version.topics[0].subtopics[0].id,
        book.chapters[0].sections[0].id,
    )


def _question(
    curriculum_version_id: int,
    topic_id: int,
    subtopic_id: int,
    section_id: int,
) -> Question:
    return Question(
        prompt="Explain why strings are immutable.",
        curriculum_version_id=curriculum_version_id,
        topic_id=topic_id,
        subtopic_id=subtopic_id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        spec={"source_section_ids": [section_id]},
        content={"sources": [{"section_id": section_id}]},
    )


def test_shared_checks_pass_for_seeded_ids(session: Session, settings: Any) -> None:
    version_id, topic_id, subtopic_id, section_id = _seed(session, settings)

    checks = check_shared(_question(version_id, topic_id, subtopic_id, section_id), session)

    assert [check.name for check in checks] == [
        "approved_taxonomy_ids",
        "source_section_ids",
        "allowed_question_type",
        "allowed_difficulty",
    ]
    assert all(check.passed for check in checks)
    assert [check.detail for check in checks] == [
        "Approved curriculum IDs",
        "Source section IDs exist",
        "Allowed question type",
        "Allowed difficulty",
    ]


def test_shared_checks_reject_unknown_section(session: Session, settings: Any) -> None:
    version_id, topic_id, subtopic_id, section_id = _seed(session, settings)
    question = _question(version_id, topic_id, subtopic_id, section_id)
    question.content = {"sources": [{"section_id": 999999}]}

    checks = {check.name: check for check in check_shared(question, session)}

    assert checks["source_section_ids"].passed is False
    assert checks["source_section_ids"].detail == "Source section IDs are missing or do not exist."


def test_shared_checks_reject_null_type(session: Session, settings: Any) -> None:
    checks = {check.name: check for check in check_shared(Question(prompt="x"), session)}

    assert checks["allowed_question_type"].passed is False
    assert checks["allowed_question_type"].detail == "Question type is not allowed."


def test_shared_checks_rejects_non_approved_curriculum(session: Session, settings: Any) -> None:
    version_id, topic_id, subtopic_id, section_id = _seed(session, settings)
    question = _question(version_id, topic_id, subtopic_id, section_id)
    version = CurriculumRepository(session).get_with_tree(version_id)
    version.status = CurriculumStatus.PROPOSED

    checks = {check.name: check for check in check_shared(question, session)}

    assert checks["approved_taxonomy_ids"].passed is False
    assert (
        checks["approved_taxonomy_ids"].detail
        == "Curriculum IDs are not an approved topic/subtopic pair."
    )
