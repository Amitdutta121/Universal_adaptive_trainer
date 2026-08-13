"""The request half and the claim half of the generation contract (ADR-031)."""

from __future__ import annotations

import book_documents as docs
import pytest
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType
from app.errors import InvalidQuestionSpecError
from app.generation.spec import (
    MAX_CLAIMED_SUBTOPICS,
    build_question_spec,
    require_approved_version,
    resolve_claimed_taxonomy,
)
from app.ingestion import BookImportService

TAXONOMY = (
    b'{"schema_version":"1","label":"T","topics":['
    b'{"name":"Strings","subtopics":['
    b'{"name":"Immutability"},{"name":"Slicing"},{"name":"Methods"},{"name":"Formatting"}]},'
    b'{"name":"Loops","subtopics":[{"name":"For loops"}]}]}'
)


def _seed(session: Session, settings):
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="tax.json", data=TAXONOMY
    )
    session.commit()
    topic = version.topics[0]
    return version, topic, topic.subtopics[0], book.chapters[0].sections[0].id


# --------------------------------------------------------------- the request half


def test_build_spec_accepts_an_approved_request(session: Session, settings) -> None:
    version, _topic, _sub, section_id = _seed(session, settings)

    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_id],
    )

    assert spec.source_section_ids == [section_id]


def test_the_spec_carries_no_taxonomy(session: Session, settings) -> None:
    """Topic and subtopics are the generator's answer, not part of the request."""
    fields = set(build_question_spec.__annotations__)
    assert "topic_id" not in fields
    assert "subtopic_ids" not in fields


def test_build_spec_rejects_multiple_source_sections(session: Session, settings) -> None:
    version, _topic, _sub, section_id = _seed(session, settings)

    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            question_type=QuestionType.DEBUGGING,
            difficulty=Difficulty.MEDIUM,
            source_section_ids=[section_id, section_id],
        )


def test_rejects_missing_section(session: Session, settings) -> None:
    version, _topic, _sub, _section_id = _seed(session, settings)

    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
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
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            source_section_ids=[1],
        )
    with pytest.raises(InvalidQuestionSpecError):
        require_approved_version(session, version.id)


# ----------------------------------------------------------------- the claim half


def test_a_valid_claim_is_accepted(session: Session, settings) -> None:
    version, topic, sub, _section_id = _seed(session, settings)

    claim = resolve_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id])

    assert claim.topic_id == topic.id
    assert claim.subtopic_ids == [sub.id]


def test_a_claim_may_name_several_subtopics(session: Session, settings) -> None:
    version, topic, _sub, _section_id = _seed(session, settings)
    ids = [subtopic.id for subtopic in topic.subtopics][:2]

    claim = resolve_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=ids)

    assert claim.subtopic_ids == ids


def test_a_repeated_subtopic_is_collapsed_not_refused(session: Session, settings) -> None:
    """Naming a subtopic twice is still one classification."""
    version, topic, sub, _section_id = _seed(session, settings)

    claim = resolve_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id, sub.id])

    assert claim.subtopic_ids == [sub.id]


def test_rejects_a_topic_outside_the_version(session: Session, settings) -> None:
    version, _topic, sub, _section_id = _seed(session, settings)

    with pytest.raises(InvalidQuestionSpecError):
        resolve_claimed_taxonomy(version, topic_id=999999, subtopic_ids=[sub.id])


def test_rejects_a_subtopic_from_another_topic(session: Session, settings) -> None:
    """A question spread across two topics has no single home in the taxonomy."""
    version, topic, sub, _section_id = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id

    with pytest.raises(InvalidQuestionSpecError):
        resolve_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id, foreign])


def test_rejects_an_unknown_subtopic(session: Session, settings) -> None:
    version, topic, sub, _section_id = _seed(session, settings)

    with pytest.raises(InvalidQuestionSpecError):
        resolve_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id, 999999])


def test_rejects_an_empty_claim(session: Session, settings) -> None:
    version, topic, _sub, _section_id = _seed(session, settings)

    with pytest.raises(InvalidQuestionSpecError):
        resolve_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[])


def test_rejects_a_claim_over_the_cap(session: Session, settings) -> None:
    """A question claiming half the taxonomy has classified nothing."""
    version, topic, _sub, _section_id = _seed(session, settings)
    too_many = [subtopic.id for subtopic in topic.subtopics][: MAX_CLAIMED_SUBTOPICS + 1]
    assert len(too_many) == MAX_CLAIMED_SUBTOPICS + 1

    with pytest.raises(InvalidQuestionSpecError):
        resolve_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=too_many)
