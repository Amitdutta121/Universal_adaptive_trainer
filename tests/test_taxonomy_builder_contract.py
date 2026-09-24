"""The two things the frontend's manual taxonomy builder depends on the backend for.

The builder (``frontend/src/app/curriculum/builder``) has no endpoint of its own: it sends a
taxonomy document to the existing import and shows the refusal it gets back. Both halves are
therefore contracts between the two codebases that nothing on either side otherwise pins:

* the **document shape** the builder emits must stay acceptable to the validator, and
* the **wording of a refusal** must stay parseable by the frontend's ``taxonomy-refusal.ts``
  (under ``frontend/src/app/curriculum``), which turns ``topics.1.subtopics.0.name: Field required``
  into a sentence a professor can act on.

If either test fails, the fix is usually on the frontend side (update the parser or the emitter),
not a reason to weaken the test.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.curriculum.taxonomy_import import TaxonomyImportService
from app.curriculum.taxonomy_schema import SCHEMA_VERSION, parse_taxonomy_document
from app.errors import InvalidTaxonomyDocumentError


def _encode(document: dict) -> bytes:
    return json.dumps(document).encode("utf-8")


def test_the_document_the_builder_emits_is_accepted_and_stored(
    session: Session, settings: Settings
) -> None:
    """`toTaxonomyDocument`: trimmed names, and a blank description sent as an empty string."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "label": "Intro",
        "topics": [
            {
                "name": "Loops",
                "description": "",
                "subtopics": [
                    {"name": "while loops", "description": ""},
                    {"name": "for loops", "description": "Iterating over sequences."},
                ],
            },
            {
                "name": "Functions",
                "description": "Reusable blocks.",
                "subtopics": [{"name": "Defining and calling", "description": ""}],
            },
        ],
    }

    version = TaxonomyImportService(session, settings).import_upload(
        filename="manual-taxonomy.json", data=_encode(document)
    )

    assert [t.name for t in version.topics] == ["Loops", "Functions"]
    loops = version.topics[0]
    # The builder's list order is the position, and a blank description is stored as none.
    assert [s.name for s in loops.subtopics] == ["while loops", "for loops"]
    assert loops.description is None
    assert loops.subtopics[0].description is None
    assert loops.subtopics[1].description == "Iterating over sequences."


def _refusal(document: dict) -> str:
    with pytest.raises(InvalidTaxonomyDocumentError) as raised:
        parse_taxonomy_document(_encode(document))
    return raised.value.detail or ""


def _doc(**overrides: object) -> dict:
    document: dict = {
        "schema_version": SCHEMA_VERSION,
        "label": "L",
        "topics": [
            {"name": "Lists", "subtopics": [{"name": "Indexing"}, {"name": "Slicing"}]},
            {"name": "Sets", "subtopics": [{"name": "Union"}]},
        ],
    }
    document.update(overrides)
    return document


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        pytest.param(
            lambda d: d["topics"][1]["subtopics"].append({"name": "union"}),
            "topics.1: Value error, duplicate subtopic name 'union'",
            id="duplicate-subtopic-names-are-reported-on-the-topic",
        ),
        pytest.param(
            lambda d: d["topics"].append({"name": "sets", "subtopics": [{"name": "x"}]}),
            "Value error, duplicate topic name 'sets'",
            id="duplicate-topic-names",
        ),
        pytest.param(
            lambda d: d["topics"][0]["subtopics"][1].update(name="x" * 301),
            "topics.0.subtopics.1.name: String should have at most 300 characters",
            id="over-long-subtopic-name",
        ),
        pytest.param(
            lambda d: d["topics"][0].pop("name"),
            "topics.0.name: Field required",
            id="missing-topic-name",
        ),
        pytest.param(
            lambda d: d.update(label=""),
            "label: String should have at least 1 character",
            id="empty-label",
        ),
        pytest.param(
            lambda d: d.update(topics=[]),
            "topics: List should have at least 1 item after validation, not 0",
            id="no-topics",
        ),
        pytest.param(
            lambda d: d["topics"][0].update(subtopics=[]),
            "topics.0.subtopics: List should have at least 1 item after validation, not 0",
            id="topic-without-subtopics",
        ),
        pytest.param(
            lambda d: d["topics"][0].update(colour="red"),
            "topics.0.colour: Extra inputs are not permitted",
            id="unknown-key",
        ),
    ],
)
def test_a_refusal_is_worded_the_way_the_frontend_parser_expects(mutate, expected: str) -> None:
    document = _doc()
    mutate(document)

    assert expected in _refusal(document)


def test_several_problems_are_joined_in_order_with_a_semicolon() -> None:
    """The frontend splits on '; ' and explains one sentence per problem."""
    document = _doc()
    document["topics"][0].pop("name")
    document["topics"][1]["subtopics"].append({"name": "union"})

    detail = _refusal(document)

    parts = detail.split("; ")
    assert len(parts) == 2
    assert parts[0].startswith("topics.0.name: ")
    assert parts[1].startswith("topics.1: ")
