"""Source retrieval: reading extracted sections back out, with citations.

This is the interface later question generation uses to fetch grounding text. It
returns domain objects rather than ORM rows, and every section it hands out can
produce a :class:`~app.domain.books.SectionSource` naming the book, chapter,
section and pages it came from.

Retrieval never chunks. A caller that needs to fit a long section into a model
context window splits it itself; the source of truth stays whole.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.books import BookChapter, BookSection, SectionSource
from app.domain.enums import StructureConfidence, StructureSource
from app.ingestion.service import decode_warnings
from app.persistence.models import BookChapterRow, BookSectionRow
from app.persistence.repositories import BookRepository, BookStructureRepository


def section_from_row(row: BookSectionRow) -> BookSection:
    """Convert a section row into its domain form."""
    return BookSection(
        id=row.id,
        book_id=row.book_id,
        chapter_id=row.chapter_id,
        number=row.number,
        title=row.title,
        position=row.position,
        text=row.text,
        start_page=row.start_page,
        end_page=row.end_page,
        structure_source=StructureSource(row.structure_source),
        declared_confidence=StructureConfidence(row.structure_confidence),
        warnings=decode_warnings(row.warnings_json),
    )


def chapter_from_row(row: BookChapterRow, *, include_sections: bool = True) -> BookChapter:
    """Convert a chapter row into its domain form."""
    return BookChapter(
        id=row.id,
        book_id=row.book_id,
        number=row.number,
        title=row.title,
        position=row.position,
        start_page=row.start_page,
        end_page=row.end_page,
        structure_source=StructureSource(row.structure_source),
        declared_confidence=StructureConfidence(row.structure_confidence),
        sections=[section_from_row(section) for section in row.sections]
        if include_sections
        else [],
    )


class SourceRetrieval:
    """Reads extracted book sources for grounding and display."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._books = BookRepository(session)
        self._structure = BookStructureRepository(session)

    def get_section(self, section_id: int) -> BookSection:
        """One section.

        Raises:
            NotFoundError: if no such section exists.
        """
        return section_from_row(self._structure.get_section(section_id))

    def sections_in_chapter(self, chapter_id: int) -> list[BookSection]:
        """Every section of one chapter, in reading order."""
        return [section_from_row(row) for row in self._structure.sections_in_chapter(chapter_id)]

    def sections_in_book(self, book_id: int) -> list[BookSection]:
        """Every section of one book, in reading order."""
        return [section_from_row(row) for row in self._structure.sections_in_book(book_id)]

    def chapters_in_book(self, book_id: int) -> list[BookChapter]:
        """The chapter tree of one book, each chapter carrying its sections."""
        return [chapter_from_row(row) for row in self._structure.chapters_in_book(book_id)]

    def section_source(self, section_id: int) -> SectionSource:
        """The citation metadata for a section.

        Raises:
            NotFoundError: if no such section exists.
        """
        row = self._structure.get_section(section_id)
        chapter = row.chapter
        return SectionSource(
            book_id=row.book_id,
            book_title=row.book.title,
            book_author=row.book.author,
            section_id=row.id,
            chapter_id=row.chapter_id,
            chapter_number=chapter.number if chapter else None,
            chapter_title=chapter.title if chapter else None,
            section_number=row.number,
            section_title=row.title,
            start_page=row.start_page,
            end_page=row.end_page,
            structure_source=StructureSource(row.structure_source),
            structure_confidence=StructureConfidence(row.structure_confidence),
        )
