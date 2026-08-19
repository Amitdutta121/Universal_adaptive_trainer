"""The instruction that produces a book document.

The prompt is only worth shipping if it describes the document this application
actually accepts, so the tests that matter here are the ones that fail when the
contract moves underneath it: the worked example is parsed by the real validator,
and every closed vocabulary is checked for a value the prompt never mentions.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import ExtractionWarningCode, StructureSource, WarningSeverity
from app.ingestion import (
    SCHEMA_VERSION,
    STRUCTURE_SOURCE_TERMS,
    SUPPORTED_EXTENSIONS,
    WARNING_CODE_TERMS,
    WARNING_SEVERITY_TERMS,
    book_authoring_prompt,
    example_json,
    parse_book_document,
)


@pytest.fixture
def prompt() -> str:
    return book_authoring_prompt(max_upload_mb=100)


class TestWorkedExample:
    def test_the_example_is_a_document_this_application_accepts(self) -> None:
        """The one claim the prompt cannot be allowed to get wrong."""
        document = parse_book_document(example_json().encode("utf-8"))
        assert document.title == "Think Python"
        assert document.section_count == 2

    def test_the_example_shows_a_section_with_no_heading(self) -> None:
        """`title: null` is the rule most likely to be broken by a producer."""
        document = parse_book_document(example_json().encode("utf-8"))
        unlabelled = document.chapters[0].sections[1]
        assert unlabelled.title is None
        assert unlabelled.number is None

    def test_the_example_declares_the_boundary_it_guessed(self) -> None:
        """A guessed boundary makes the book partial; the example must show that."""
        document = parse_book_document(example_json().encode("utf-8"))
        assert document.is_partial()

    def test_the_example_keeps_leading_whitespace(self) -> None:
        """Section text is stored verbatim, code listing indentation included."""
        document = parse_book_document(example_json().encode("utf-8"))
        assert document.chapters[0].sections[1].text.startswith("    print(")

    def test_the_example_is_indented_json(self) -> None:
        assert json.loads(example_json())
        assert "\n  " in example_json()


class TestPromptContent:
    def test_it_names_the_schema_version_the_validator_requires(self, prompt: str) -> None:
        assert f'"{SCHEMA_VERSION}"' in prompt

    def test_it_embeds_the_worked_example(self, prompt: str) -> None:
        assert example_json() in prompt

    @pytest.mark.parametrize(
        "vocabulary",
        [StructureSource, ExtractionWarningCode, WarningSeverity],
        ids=["structure_source", "warning_code", "severity"],
    )
    def test_every_vocabulary_value_is_described(self, prompt: str, vocabulary: type) -> None:
        """A value the prompt never mentions is one a producer cannot choose."""
        for member in vocabulary:
            assert f'"{member.value}"' in prompt, f"{member.value} is missing from the prompt"

    def test_every_vocabulary_value_carries_a_meaning(self) -> None:
        terms = (*STRUCTURE_SOURCE_TERMS, *WARNING_CODE_TERMS, *WARNING_SEVERITY_TERMS)
        assert all(term.meaning.strip() for term in terms)
        assert len(STRUCTURE_SOURCE_TERMS) == len(StructureSource)
        assert len(WARNING_CODE_TERMS) == len(ExtractionWarningCode)
        assert len(WARNING_SEVERITY_TERMS) == len(WarningSeverity)

    def test_it_forbids_inventing_text_and_headings(self, prompt: str) -> None:
        """The two rules that would otherwise poison generated questions."""
        assert "VERBATIM" in prompt
        assert "Never invent a heading" in prompt

    def test_it_states_the_upload_limit_it_was_built_with(self) -> None:
        assert "at most 7 MB" in book_authoring_prompt(max_upload_mb=7)
        assert ", ".join(SUPPORTED_EXTENSIONS) in book_authoring_prompt(max_upload_mb=7)


class TestDocumentGuideEndpoint:
    def test_it_serves_the_prompt_and_the_example(self, client: TestClient) -> None:
        response = client.get("/api/books/document-guide")
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == SCHEMA_VERSION
        assert body["supported_extensions"] == list(SUPPORTED_EXTENSIONS)
        assert body["max_upload_mb"] > 0
        assert "book JSON document" in body["prompt"]
        assert body["example_json"] == example_json()

    def test_it_serves_the_vocabularies_a_client_would_otherwise_hard_code(
        self, client: TestClient
    ) -> None:
        body = client.get("/api/books/document-guide").json()
        assert [term["value"] for term in body["structure_sources"]] == [
            member.value for member in StructureSource
        ]
        assert all(term["meaning"] for term in body["warning_codes"])
        assert [term["value"] for term in body["warning_severities"]] == [
            member.value for member in WarningSeverity
        ]

    def test_the_example_it_serves_imports(self, client: TestClient) -> None:
        """End to end: what the page shows is what the upload endpoint accepts."""
        example = client.get("/api/books/document-guide").json()["example_json"]
        response = client.post(
            "/api/books",
            files={"file": ("example.json", example.encode("utf-8"), "application/json")},
        )
        assert response.status_code == 201, response.text
        # It declares a guessed boundary, so it is imported with caveats.
        assert response.json()["status"] == "partial"

    def test_the_route_is_not_shadowed_by_the_book_id_route(self, client: TestClient) -> None:
        """`/books/document-guide` must not be read as a book id."""
        assert client.get("/api/books/document-guide").status_code == 200
        assert client.get("/api/books/999999").status_code == 404
