from pathlib import Path

import pytest

from app.curriculum.taxonomy_schema import SCHEMA_VERSION, parse_taxonomy_document
from app.errors import InvalidTaxonomyDocumentError

EXAMPLE = Path("docs/taxonomy_document_example.json")


def test_example_document_is_valid() -> None:
    doc = parse_taxonomy_document(EXAMPLE.read_bytes())
    assert doc.schema_version == SCHEMA_VERSION
    assert doc.topics
    assert all(topic.subtopics for topic in doc.topics)


def test_unknown_field_is_rejected() -> None:
    raw = (
        b'{"schema_version":"1","label":"X","topics":[{"name":"T",'
        b'"subtopics":[{"name":"S"}]}],"extra":1}'
    )
    with pytest.raises(InvalidTaxonomyDocumentError):
        parse_taxonomy_document(raw)


def test_empty_topics_rejected() -> None:
    raw = b'{"schema_version":"1","label":"X","topics":[]}'
    with pytest.raises(InvalidTaxonomyDocumentError):
        parse_taxonomy_document(raw)


def test_duplicate_topic_names_rejected() -> None:
    raw = (
        b'{"schema_version":"1","label":"X","topics":['
        b'{"name":"Loops","subtopics":[{"name":"A"}]},'
        b'{"name":"loops","subtopics":[{"name":"B"}]}]}'
    )
    with pytest.raises(InvalidTaxonomyDocumentError):
        parse_taxonomy_document(raw)


def test_wrong_schema_version_rejected() -> None:
    raw = b'{"schema_version":"99","label":"X","topics":[{"name":"T","subtopics":[{"name":"S"}]}]}'
    with pytest.raises(InvalidTaxonomyDocumentError):
        parse_taxonomy_document(raw)
