"""Taxonomy import: validate upload bytes and persist an APPROVED curriculum version."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.curriculum.taxonomy_import import TaxonomyImportService
from app.domain.enums import CurriculumItemStatus, CurriculumStatus
from app.errors import InvalidTaxonomyDocumentError, UnsupportedFileError
from app.persistence.repositories import CurriculumRepository

VALID = (
    b'{"schema_version":"1","label":"Demo","topics":['
    b'{"name":"Loops","description":"Iteration.","subtopics":['
    b'{"name":"While loops","description":"Condition-controlled."},'
    b'{"name":"For loops"}]}]}'
)


def test_import_writes_approved_version(session: Session, settings: Settings) -> None:
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json", data=VALID
    )
    session.commit()
    assert version.status is CurriculumStatus.APPROVED
    assert version.approved_at is not None
    assert version.generated_by == "taxonomy-upload"
    assert version.label == "Demo"
    assert len(version.topics) == 1
    topic = version.topics[0]
    assert topic.review_status is CurriculumItemStatus.ACCEPTED
    assert topic.stable_id and topic.stable_id.startswith("top-")
    assert {s.name for s in topic.subtopics} == {"While loops", "For loops"}
    assert all(s.review_status is CurriculumItemStatus.ACCEPTED for s in topic.subtopics)
    assert all(s.stable_id.startswith("sub-") for s in topic.subtopics)
    assert CurriculumRepository(session).get_approved().id == version.id


def test_identical_document_reimport_keeps_same_stable_ids(
    session: Session, settings: Settings
) -> None:
    first = TaxonomyImportService(session, settings).import_upload(filename="a.json", data=VALID)
    session.commit()
    second = TaxonomyImportService(session, settings).import_upload(filename="b.json", data=VALID)
    session.commit()
    assert first.id != second.id
    assert first.topics[0].stable_id == second.topics[0].stable_id
    assert {s.stable_id for s in first.topics[0].subtopics} == {
        s.stable_id for s in second.topics[0].subtopics
    }
    assert CurriculumRepository(session).get_approved().id == second.id


def test_invalid_document_creates_no_curriculum_version(
    session: Session, settings: Settings
) -> None:
    with pytest.raises(InvalidTaxonomyDocumentError):
        TaxonomyImportService(session, settings).import_upload(
            filename="bad.json", data=b'{"schema_version":"1","label":"X","topics":[]}'
        )
    assert CurriculumRepository(session).count() == 0


def test_non_json_extension_rejected(session: Session, settings: Settings) -> None:
    with pytest.raises(UnsupportedFileError):
        TaxonomyImportService(session, settings).import_upload(filename="taxonomy.txt", data=VALID)
    assert CurriculumRepository(session).count() == 0
