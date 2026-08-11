"""The retrieval layer and source traceability.

This is the contract later question generation depends on: given a section, it
must be able to fetch the text and say exactly where it came from.
"""

from __future__ import annotations

import book_documents as docs
import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import StructureConfidence, StructureSource
from app.errors import NotFoundError
from app.ingestion import BookImportService, SourceRetrieval
from app.persistence.models import BookRow
from app.persistence.repositories import BookStructureRepository


@pytest.fixture
def book(session: Session, settings: Settings) -> BookRow:
    row = BookImportService(session, settings).import_upload(
        filename="think_python.json", data=docs.to_bytes(docs.think_python())
    )
    session.commit()
    return row


@pytest.fixture
def retrieval(session: Session) -> SourceRetrieval:
    return SourceRetrieval(session)


class TestRetrieveOneSection:
    def test_returns_the_section_with_its_text(
        self, book: BookRow, retrieval: SourceRetrieval, session: Session
    ) -> None:
        section_id = BookStructureRepository(session).sections_in_book(book.id)[0].id
        section = retrieval.get_section(section_id)
        assert section.number == "1.1"
        assert section.title == "What Is a Program?"
        assert section.text == "A program is a sequence of instructions."

    def test_unknown_section_raises(self, retrieval: SourceRetrieval) -> None:
        with pytest.raises(NotFoundError):
            retrieval.get_section(999_999)


class TestRetrieveByChapterAndBook:
    def test_all_sections_in_a_chapter(
        self, book: BookRow, retrieval: SourceRetrieval, session: Session
    ) -> None:
        chapters = BookStructureRepository(session).chapters_in_book(book.id)
        sections = retrieval.sections_in_chapter(chapters[1].id)
        assert [section.number for section in sections] == ["2.1", "2.2"]

    def test_all_sections_in_a_book_in_reading_order(
        self, book: BookRow, retrieval: SourceRetrieval
    ) -> None:
        sections = retrieval.sections_in_book(book.id)
        assert [section.number for section in sections] == ["1.1", "1.2", "2.1", "2.2"]

    def test_chapter_tree_carries_its_sections(
        self, book: BookRow, retrieval: SourceRetrieval
    ) -> None:
        chapters = retrieval.chapters_in_book(book.id)
        assert [chapter.display_title() for chapter in chapters] == [
            "1 The Way of the Program",
            "2 Variables, Expressions and Statements",
        ]
        assert [len(chapter.sections) for chapter in chapters] == [2, 2]

    def test_sections_of_an_unknown_book_are_empty(self, retrieval: SourceRetrieval) -> None:
        assert retrieval.sections_in_book(999_999) == []


class TestSourceTraceability:
    def test_source_names_book_chapter_section_and_pages(
        self, book: BookRow, retrieval: SourceRetrieval, session: Session
    ) -> None:
        section_id = BookStructureRepository(session).sections_in_book(book.id)[2].id
        source = retrieval.section_source(section_id)

        assert source.book_id == book.id
        assert source.book_title == "Think Python"
        assert source.book_author == "Allen B. Downey"
        assert source.chapter_number == "2"
        assert source.chapter_title == "Variables, Expressions and Statements"
        assert source.section_number == "2.1"
        assert source.section_title == "Values and Types"
        assert source.start_page == 31
        assert source.end_page == 33
        assert source.location_label == "Pages 31\u201333"

    def test_source_records_where_the_boundary_came_from(
        self, book: BookRow, retrieval: SourceRetrieval, session: Session
    ) -> None:
        section_id = BookStructureRepository(session).sections_in_book(book.id)[0].id
        source = retrieval.section_source(section_id)
        assert source.structure_source is StructureSource.PDF_OUTLINE
        assert source.structure_confidence is StructureConfidence.HIGH

    def test_citation_is_human_readable(
        self, book: BookRow, retrieval: SourceRetrieval, session: Session
    ) -> None:
        section_id = BookStructureRepository(session).sections_in_book(book.id)[0].id
        citation = retrieval.section_source(section_id).citation()
        assert citation == (
            "Think Python, 1 The Way of the Program, 1.1 What Is a Program? (Pages 17\u201318)"
        )

    def test_every_section_is_traceable(self, book: BookRow, retrieval: SourceRetrieval) -> None:
        """No section may exist without a route back to its book and location."""
        for section in retrieval.sections_in_book(book.id):
            assert section.id is not None
            source = retrieval.section_source(section.id)
            assert source.book_id == book.id
            assert source.start_page is not None
            assert source.citation()

    def test_unknown_section_source_raises(self, retrieval: SourceRetrieval) -> None:
        with pytest.raises(NotFoundError):
            retrieval.section_source(999_999)


class TestTraceabilityOfUncertainUnits:
    """A guessed unit is still traceable, and still honest about being uncertain."""

    @pytest.fixture
    def uncertain_book(self, session: Session, settings: Settings) -> BookRow:
        row = BookImportService(session, settings).import_upload(
            filename="uncertain.json", data=docs.to_bytes(docs.with_caveats())
        )
        session.commit()
        return row

    def test_untitled_section_still_cites_its_book_and_page(
        self, uncertain_book: BookRow, retrieval: SourceRetrieval, session: Session
    ) -> None:
        section_id = BookStructureRepository(session).sections_in_book(uncertain_book.id)[0].id
        source = retrieval.section_source(section_id)

        assert source.section_title is None
        assert source.book_title == "Uncertain Book"
        assert source.start_page == 1
        assert source.citation() == "Uncertain Book (Pages 1\u20132)"

    def test_guessed_units_report_low_confidence(
        self, uncertain_book: BookRow, retrieval: SourceRetrieval, session: Session
    ) -> None:
        section_id = BookStructureRepository(session).sections_in_book(uncertain_book.id)[0].id
        source = retrieval.section_source(section_id)
        assert source.structure_confidence is StructureConfidence.LOW
        assert source.structure_source is StructureSource.PRODUCER_INFERRED

    def test_section_level_warnings_survive_the_round_trip(
        self, uncertain_book: BookRow, retrieval: SourceRetrieval, session: Session
    ) -> None:
        section_id = BookStructureRepository(session).sections_in_book(uncertain_book.id)[0].id
        section = retrieval.get_section(section_id)
        assert [warning.code for warning in section.warnings] == ["missing_heading"]
