"""The instruction that produces a taxonomy document.

The guide is only worth shipping if it describes the document this application
actually accepts, so the tests that matter here are the ones that fail when the
contract moves underneath it: the worked example is parsed by the real validator
and posted to the real endpoint, and every field of every model is checked for a
bound the guide never mentions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.curriculum import (
    ALL_FIELDS,
    DOCUMENT_FIELDS,
    EXAMPLE_DOCUMENT,
    SCHEMA_VERSION,
    SUBTOPIC_FIELDS,
    SUPPORTED_EXTENSIONS,
    TOPIC_FIELDS,
    example_json,
    parse_taxonomy_document,
    taxonomy_authoring_prompt,
)
from app.curriculum.taxonomy_schema import TaxonomyDocument, TaxonomySubtopic, TaxonomyTopic

DOCS_EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "taxonomy_document_example.json"


@pytest.fixture
def prompt() -> str:
    return taxonomy_authoring_prompt(max_upload_mb=100)


class TestWorkedExample:
    def test_the_example_is_a_document_this_application_accepts(self) -> None:
        """The one claim the guide cannot be allowed to get wrong."""
        document = parse_taxonomy_document(example_json().encode("utf-8"))
        assert document.label == "Introductory Python"
        assert len(document.topics) == 2
        assert sum(len(topic.subtopics) for topic in document.topics) == 5

    def test_the_example_declares_the_schema_version_the_contract_names(self) -> None:
        """Interpolated rather than written out, so a bump cannot leave it stale."""
        assert EXAMPLE_DOCUMENT["schema_version"] == SCHEMA_VERSION

    def test_the_documented_example_is_the_served_example(self) -> None:
        """One example, two surfaces, so the docs file cannot drift from the guide."""
        assert DOCS_EXAMPLE.is_file(), "docs/taxonomy_document_example.json is missing"
        on_disk = json.loads(DOCS_EXAMPLE.read_text(encoding="utf-8"))
        assert on_disk == EXAMPLE_DOCUMENT


class TestFieldReference:
    @pytest.mark.parametrize(
        ("model", "limits"),
        [
            (TaxonomyDocument, DOCUMENT_FIELDS),
            (TaxonomyTopic, TOPIC_FIELDS),
            (TaxonomySubtopic, SUBTOPIC_FIELDS),
        ],
    )
    def test_every_field_of_the_contract_is_described(self, model: type, limits: tuple) -> None:
        """A field added to the schema must not go missing from the guide.

        The module raises at import when a meaning is absent, so this asserts the
        coverage that protects rather than the exception -- if the guide ever
        stops describing a field, this is what says so.
        """
        described = {limit.path.rsplit(".", 1)[-1] for limit in limits}
        assert described == set(model.model_fields)

    def test_every_limit_carries_a_professor_facing_meaning(self) -> None:
        assert all(limit.meaning.strip() for limit in ALL_FIELDS)

    def test_the_bounds_come_from_the_models_rather_than_from_prose(self) -> None:
        by_path = {limit.path: limit for limit in ALL_FIELDS}
        assert by_path["label"].max_length == 200
        assert by_path["topics[].name"].max_length == 300
        assert by_path["topics[].subtopics[].description"].max_length == 2000
        # A list bound counts items, not characters.
        assert by_path["topics[].subtopics"].kind == "list"
        assert by_path["topics[].subtopics"].min_length == 1

    def test_optional_fields_are_marked_optional(self) -> None:
        by_path = {limit.path: limit for limit in ALL_FIELDS}
        assert by_path["topics[].description"].required is False
        assert by_path["topics[].name"].required is True


class TestPromptContent:
    def test_it_names_the_schema_version(self, prompt: str) -> None:
        assert f'"{SCHEMA_VERSION}"' in prompt

    def test_it_embeds_the_worked_example(self, prompt: str) -> None:
        assert example_json() in prompt

    @pytest.mark.parametrize("limit", ALL_FIELDS, ids=lambda limit: limit.path)
    def test_it_states_every_bound_the_validator_enforces(self, prompt: str, limit) -> None:
        assert f"`{limit.path}`" in prompt
        if limit.max_length is not None:
            assert str(limit.max_length) in prompt

    def test_it_states_the_two_rules_a_producer_cannot_guess(self, prompt: str) -> None:
        """No closed vocabularies here -- these are what a book's would have been."""
        assert "never" in prompt and "ignored" in prompt  # extra="forbid"
        assert "normalising case" in prompt  # duplicate names

    def test_it_states_the_upload_limit_and_extension_it_was_given(self) -> None:
        prompt = taxonomy_authoring_prompt(max_upload_mb=7)
        assert "at most 7 MB" in prompt
        for extension in SUPPORTED_EXTENSIONS:
            assert extension in prompt


class TestDocumentGuideEndpoint:
    def test_it_serves_the_contract(self, client: TestClient) -> None:
        response = client.get("/api/curriculum/document-guide")
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == SCHEMA_VERSION
        assert body["supported_extensions"] == list(SUPPORTED_EXTENSIONS)
        assert body["max_upload_mb"] > 0
        assert body["example_json"] == example_json()
        assert len(body["fields"]) == len(ALL_FIELDS)

    def test_it_says_the_upload_is_not_retained(self, client: TestClient) -> None:
        """Unlike a book's document, so a client must not offer a download."""
        assert client.get("/api/curriculum/document-guide").json()["retains_upload"] is False

    def test_the_example_it_serves_is_one_the_import_accepts(self, client: TestClient) -> None:
        """End to end: what the guide hands out is what the validator takes."""
        served = client.get("/api/curriculum/document-guide").json()["example_json"]
        response = client.post(
            "/api/curriculum/versions",
            files={"file": ("taxonomy.json", served.encode("utf-8"), "application/json")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["version"]["status"] == "approved"

    def test_the_route_is_not_shadowed_by_the_version_lookup(self, client: TestClient) -> None:
        assert client.get("/api/curriculum/document-guide").status_code == 200

