"""The book document contract.

Validation is the whole of ingestion now, so these tests are the safety net that
replaced heuristic-extraction tests: every way a document can be wrong must be
rejected with a message that names the problem.
"""

from __future__ import annotations

import json
from copy import deepcopy

import book_documents as docs
import pytest

from app.domain.enums import StructureConfidence, StructureSource
from app.errors import InvalidBookDocumentError
from app.ingestion import SCHEMA_VERSION, parse_book_document


def parse(document: dict) -> object:
    return parse_book_document(docs.to_bytes(document))


class TestValidDocuments:
    def test_accepts_a_well_formed_document(self) -> None:
        document = parse(docs.think_python())
        assert document.title == "Think Python"
        assert document.author == "Allen B. Downey"
        assert document.page_count == 292
        assert len(document.chapters) == 2
        assert document.section_count == 4

    def test_accepts_the_minimal_document(self) -> None:
        document = parse(docs.minimal())
        assert document.section_count == 1
        assert document.chapters[0].number is None
        assert document.chapters[0].title is None

    def test_section_positions_are_book_wide(self) -> None:
        """Ordering by position alone must give true reading order."""
        chapters = parse(docs.think_python()).to_domain_chapters()
        positions = [section.position for chapter in chapters for section in chapter.sections]
        assert positions == [0, 1, 2, 3]

    def test_confidence_follows_the_declared_source(self) -> None:
        chapters = parse(docs.think_python()).to_domain_chapters()
        section = chapters[0].sections[0]
        assert section.structure_source is StructureSource.PDF_OUTLINE
        assert section.structure_confidence is StructureConfidence.HIGH

    def test_an_explicit_confidence_overrides_the_source(self) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["confidence"] = "medium"
        chapters = parse(document).to_domain_chapters()
        assert chapters[0].sections[0].structure_confidence is StructureConfidence.MEDIUM

    def test_a_null_title_is_allowed_and_preserved(self) -> None:
        """A source with no heading must be representable without inventing one."""
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["title"] = None
        section = parse(document).to_domain_chapters()[0].sections[0]
        assert section.title is None
        assert section.has_detected_heading is False


class TestPartialDetection:
    def test_a_clean_document_is_not_partial(self) -> None:
        assert parse(docs.think_python()).is_partial() is False

    def test_declared_defects_make_it_partial(self) -> None:
        assert parse(docs.with_caveats()).is_partial() is True

    def test_a_guessed_boundary_makes_it_partial(self) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["structure_source"] = "producer_inferred"
        assert parse(document).is_partial() is True

    def test_informational_warnings_do_not_make_it_partial(self) -> None:
        """A badge that is always on would teach the professor to ignore it."""
        document = parse(docs.informational_only())
        assert document.warnings
        assert document.declared_defects() == []
        assert document.is_partial() is False

    def test_a_section_level_defect_makes_it_partial(self) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["warnings"] = [
            {"code": "section_text_truncated", "message": "Shortened.", "severity": "defect"}
        ]
        assert parse(document).is_partial() is True


class TestRejectsMalformedInput:
    def test_rejects_empty_bytes(self) -> None:
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse_book_document(b"")
        assert "empty" in exc.value.message

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(InvalidBookDocumentError):
            parse_book_document(b"   \n  ")

    def test_rejects_invalid_json_and_says_where(self) -> None:
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse_book_document(b'{"title": "Broken",}')
        assert "not valid JSON" in exc.value.message
        assert "line" in (exc.value.detail or "")

    def test_rejects_non_utf8_bytes(self) -> None:
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse_book_document(b'{"title": "\xff\xfe"}')
        assert "UTF-8" in exc.value.message

    def test_rejects_a_json_array(self) -> None:
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse_book_document(b"[1, 2, 3]")
        assert "must be a JSON object" in exc.value.message

    def test_rejects_a_pdf_uploaded_as_json(self) -> None:
        with pytest.raises(InvalidBookDocumentError):
            parse_book_document(b"%PDF-1.4\nnot json at all")


class TestSchemaVersion:
    def test_rejects_a_missing_version(self) -> None:
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(docs.without(docs.minimal(), "schema_version"))
        assert "schema_version" in exc.value.message
        assert SCHEMA_VERSION in (exc.value.detail or "")

    def test_rejects_an_unknown_version_as_a_version_problem(self) -> None:
        """A future document must not produce a confusing pile of field errors."""
        document = docs.minimal()
        document["schema_version"] = "2"
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(document)
        assert "Unsupported book document schema version" in exc.value.message


class TestRejectsInvalidStructure:
    def test_rejects_a_missing_title(self) -> None:
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(docs.without(docs.minimal(), "title"))
        assert "title" in (exc.value.detail or "")

    def test_rejects_an_empty_title(self) -> None:
        document = docs.minimal()
        document["title"] = "  "
        with pytest.raises(InvalidBookDocumentError):
            parse(document)

    def test_rejects_a_document_with_no_chapters(self) -> None:
        document = docs.minimal()
        document["chapters"] = []
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(document)
        assert "chapters" in (exc.value.detail or "")

    def test_rejects_a_chapter_with_no_sections(self) -> None:
        """The section is the unit, so a chapter without one grounds nothing."""
        document = docs.minimal()
        document["chapters"][0]["sections"] = []
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(document)
        assert "sections" in (exc.value.detail or "")

    def test_rejects_a_section_with_no_text(self) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["text"] = ""
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(document)
        assert "text" in (exc.value.detail or "")

    def test_rejects_a_section_missing_text_entirely(self) -> None:
        document = docs.minimal()
        del document["chapters"][0]["sections"][0]["text"]
        with pytest.raises(InvalidBookDocumentError):
            parse(document)

    def test_rejects_an_unknown_field(self) -> None:
        """A typo must be an error, not a silently ignored field."""
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["txet"] = "typo"
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(document)
        assert "txet" in (exc.value.detail or "")

    def test_rejects_a_backwards_page_range(self) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["start_page"] = 10
        document["chapters"][0]["sections"][0]["end_page"] = 4
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(document)
        assert "end_page" in (exc.value.detail or "")

    def test_rejects_a_zero_page_number(self) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["start_page"] = 0
        with pytest.raises(InvalidBookDocumentError):
            parse(document)

    def test_rejects_an_unknown_structure_source(self) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["structure_source"] = "vibes"
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(document)
        assert "structure_source" in (exc.value.detail or "")

    def test_rejects_an_unknown_warning_code(self) -> None:
        document = docs.minimal()
        document["warnings"] = [{"code": "made_up", "message": "x"}]
        with pytest.raises(InvalidBookDocumentError):
            parse(document)

    def test_reports_several_problems_at_once(self) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["text"] = ""
        document["chapters"][0]["sections"][0]["start_page"] = 0
        with pytest.raises(InvalidBookDocumentError) as exc:
            parse(document)
        assert (exc.value.detail or "").count(";") >= 1


class TestShippedExample:
    """The documented example must stay valid, or the documentation is a lie."""

    def test_the_example_document_validates(self) -> None:
        from pathlib import Path

        example = Path(__file__).resolve().parent.parent / "docs" / "book_document_example.json"
        assert example.is_file(), "docs/book_document_example.json is missing"

        document = parse_book_document(example.read_bytes())
        assert document.title == "Think Python"
        assert document.section_count == 4

    def test_the_example_demonstrates_an_unlabelled_unit(self) -> None:
        """The example must show how to represent a missing heading honestly."""
        from pathlib import Path

        example = Path(__file__).resolve().parent.parent / "docs" / "book_document_example.json"
        sections = parse_book_document(example.read_bytes()).sections
        assert any(section.title is None for section in sections)


class TestDeterminism:
    def test_the_same_document_always_parses_to_the_same_rows(self) -> None:
        """The point of a declared structure: no run-to-run variation."""
        payload = docs.think_python()
        first = parse(deepcopy(payload)).to_domain_chapters()
        second = parse(deepcopy(payload)).to_domain_chapters()
        assert [c.model_dump() for c in first] == [c.model_dump() for c in second]

    def test_key_order_does_not_change_the_result(self) -> None:
        payload = docs.think_python()
        reordered = json.loads(json.dumps(payload, sort_keys=True))
        assert parse(payload).section_count == parse(reordered).section_count
