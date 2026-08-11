"""The ingestion workflow: validate, then store.

One entry point, :meth:`BookImportService.import_upload`. There is no extraction
step: the uploaded document already declares its structure, so this validates it
and writes the rows.

Failure handling is deliberate, and everything is checked **before** the first
row is written:

* an unsupported or oversized file is rejected outright;
* a document that fails schema validation is rejected in full, with the offending
  fields named -- a half-valid book is never partially imported;
* a document that validates but declares caveats is stored as ``PARTIAL``, never
  as a clean ``IMPORTED``.

Because validation precedes storage, every book row in the database is one whose
structure validated. That is why there is no ``FAILED`` book status.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.enums import BookStatus
from app.ingestion.schema import BookDocument, parse_book_document
from app.ingestion.storage import checksum, store_upload, validate_upload
from app.persistence.models import BookChapterRow, BookRow, BookSectionRow
from app.persistence.repositories import BookRepository, BookStructureRepository

logger = logging.getLogger(__name__)


class BookImportService:
    """Imports structured book documents into the source model."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._books = BookRepository(session)
        self._structure = BookStructureRepository(session)

    def import_upload(self, *, filename: str, data: bytes, title: str | None = None) -> BookRow:
        """Validate and store one uploaded book document.

        Args:
            filename: the name the professor's browser supplied.
            data: the file's bytes, expected to be a UTF-8 JSON book document.
            title: an optional professor-supplied title, which overrides the one
                in the document.

        Returns:
            The persisted book row, in ``IMPORTED`` or ``PARTIAL`` status.

        Raises:
            UnsupportedFileError: the file type is not supported.
            FileTooLargeError: the file exceeds the configured limit.
            InvalidBookDocumentError: the JSON does not satisfy the schema.
        """
        source_format = validate_upload(filename, data, self._settings)
        # Validate the structure before storing anything, so a bad document
        # leaves behind neither a file nor a row.
        document = parse_book_document(data)

        stored_name, stored_path = store_upload(data, filename, self._settings)
        book = self._books.add(
            BookRow(
                title=(title or "").strip() or document.title,
                author=document.author,
                original_filename=filename,
                stored_filename=stored_name,
                source_format=source_format,
                file_size_bytes=len(data),
                checksum_sha256=checksum(data),
                source_filename=document.source_filename,
                producer=document.producer,
                page_count=document.page_count,
                status=BookStatus.PARTIAL if document.is_partial() else BookStatus.IMPORTED,
                warnings=[warning.to_domain() for warning in document.warnings],
                imported_at=datetime.now(UTC),
            )
        )
        self._session.flush()
        self._persist_structure(book, document)

        logger.info(
            "Imported book %s from %s: %d chapter(s), %d section(s), status=%s",
            book.id,
            stored_path.name,
            len(document.chapters),
            document.section_count,
            book.status,
        )
        return book

    def replace_structure(self, book: BookRow, document: BookDocument) -> BookRow:
        """Re-import a corrected document over an existing book.

        Used when a producer is fixed and the same book is re-converted: the rows
        are replaced rather than duplicated, and the book keeps its identity so
        anything already referring to it stays valid.
        """
        book.title = document.title
        book.author = document.author
        book.page_count = document.page_count
        book.source_filename = document.source_filename
        book.producer = document.producer
        book.status = BookStatus.PARTIAL if document.is_partial() else BookStatus.IMPORTED
        book.warnings = [warning.to_domain() for warning in document.warnings]
        book.imported_at = datetime.now(UTC)
        self._persist_structure(book, document)
        return book

    def _persist_structure(self, book: BookRow, document: BookDocument) -> None:
        """Write the document's chapter/section tree, replacing any prior one."""
        chapter_rows: list[BookChapterRow] = []
        section_rows: list[BookSectionRow] = []

        for chapter in document.to_domain_chapters():
            chapter_row = BookChapterRow(
                number=chapter.number,
                title=chapter.title,
                position=chapter.position,
                start_page=chapter.start_page,
                end_page=chapter.end_page,
                structure_source=chapter.structure_source,
                structure_confidence=chapter.structure_confidence,
            )
            chapter_rows.append(chapter_row)
            for section in chapter.sections:
                section_rows.append(
                    BookSectionRow(
                        chapter=chapter_row,
                        number=section.number,
                        title=section.title,
                        position=section.position,
                        text=section.text,
                        char_count=section.char_count,
                        start_page=section.start_page,
                        end_page=section.end_page,
                        structure_source=section.structure_source,
                        structure_confidence=section.structure_confidence,
                        warnings=section.warnings,
                    )
                )

        self._structure.replace_structure(book, chapter_rows, section_rows)
