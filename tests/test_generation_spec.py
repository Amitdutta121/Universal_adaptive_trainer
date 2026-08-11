from __future__ import annotations

import book_documents as docs
import pytest
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType
from app.errors import InvalidQuestionSpecError
from app.generation.spec import build_question_spec
from app.ingestion import BookImportService


def _seed(session: Session, settings):
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    taxonomy = (
        b'{"schema_version":"1","label":"T","topics":['
        b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="tax.json", data=taxonomy
    )
    session.commit()
    topic = version.topics[0]
    sub = topic.subtopics[0]
    section_id = book.chapters[0].sections[0].id
    return version, topic, sub, section_id


def test_build_spec_accepts_approved_ids(session: Session, settings) -> None:
    version, topic, sub, section_id = _seed(session, settings)
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[sub.id],
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_id],
    )
    assert spec.source_section_ids == [section_id]


def test_rejects_unapproved_topic(session: Session, settings) -> None:
    version, _topic, sub, section_id = _seed(session, settings)
    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            topic_id=999999,
            subtopic_ids=[sub.id],
            question_type=QuestionType.DEBUGGING,
            difficulty=Difficulty.MEDIUM,
            source_section_ids=[section_id],
        )


def test_rejects_subtopic_from_other_topic(session: Session, settings) -> None:
    version, topic, sub, section_id = _seed(session, settings)
    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            topic_id=topic.id,
            subtopic_ids=[sub.id, 999999],
            question_type=QuestionType.CODING,
            difficulty=Difficulty.EASY,
            source_section_ids=[section_id],
        )


def test_rejects_missing_section(session: Session, settings) -> None:
    version, topic, sub, _section_id = _seed(session, settings)
    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            topic_id=topic.id,
            subtopic_ids=[sub.id],
            question_type=QuestionType.TRUE_FALSE,
            difficulty=Difficulty.HARD,
            source_section_ids=[999999],
        )


def test_rejects_non_approved_curriculum_version(session: Session, settings) -> None:
    from app.domain.enums import CurriculumStatus
    from app.persistence.models import CurriculumVersionRow

    version = CurriculumVersionRow(
        label="draft",
        status=CurriculumStatus.PROPOSED,
        approved_at=None,
    )
    session.add(version)
    session.commit()
    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            topic_id=1,
            subtopic_ids=[1],
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            source_section_ids=[1],
        )
