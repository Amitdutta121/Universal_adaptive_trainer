"""The ingestion workflow: validate, then store.

One entry point, :meth:`BookImportService.import_upload`. A JSON upload already
declares its structure, so this only validates and writes the rows. A PDF
upload does not declare anything the application can read directly, so it is
first turned into that same declared shape by :mod:`app.ingestion.pdf` (ADR-048)
-- once that step hands back a document, the rest of the workflow below is
identical for both.

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
from app.domain.enums import BookStatus, SourceFormat
from app.ingestion.pdf import check_pdf_readable, extract_book_document
from app.ingestion.schema import BookDocument, parse_book_document
from app.ingestion.storage import (
    checksum,
    resolve_stored_path,
    store_upload,
    validate_upload,
)
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

    def import_upload(
        self,
        *,
        filename: str,
        data: bytes,
        title: str | None = None,
        course_id: int | None = None,
    ) -> BookRow:
        """Validate and store one uploaded book document.

        Args:
            filename: the name the professor's browser supplied.
            data: the file's bytes -- a UTF-8 JSON book document, or a PDF.
            title: an optional professor-supplied title, which overrides the one
                in the document.
            course_id: the course the book is imported into.

        Returns:
            The persisted book row, in ``IMPORTED`` or ``PARTIAL`` status.

        Raises:
            UnsupportedFileError: the file type is not supported.
            FileTooLargeError: the file exceeds the configured limit.
            InvalidBookDocumentError: the document does not satisfy the schema,
                or the PDF could not be read.
        """
        source_format = validate_upload(filename, data, self._settings)
        # Validate the structure before storing anything, so a bad document
        # leaves behind neither a file nor a row.
        document = self._read_document(data, filename, source_format)
        stored_name, _ = store_upload(data, filename, self._settings)
        return self._create_book(
            document,
            data=data,
            filename=filename,
            stored_name=stored_name,
            source_format=source_format,
            title=title,
            course_id=course_id,
        )

    def check_upload(self, *, filename: str, data: bytes) -> SourceFormat:
        """The checks quick enough to answer while the professor waits.

        Type and size; a JSON document is validated in full (parsing it is cheap), a PDF
        is only opened. What remains -- extracting a PDF's text, writing the rows -- is
        :meth:`import_stored`, which a background job runs.

        Raises:
            UnsupportedFileError, FileTooLargeError, InvalidBookDocumentError: as
                :meth:`import_upload`.
        """
        source_format = validate_upload(filename, data, self._settings)
        if source_format is SourceFormat.BOOK_PDF:
            check_pdf_readable(data)
        else:
            parse_book_document(data)
        return source_format

    def import_stored(
        self,
        *,
        stored_filename: str,
        filename: str,
        title: str | None = None,
        course_id: int | None = None,
    ) -> BookRow:
        """Import an upload :meth:`check_upload` accepted and the caller already stored.

        Raises:
            InvalidBookDocumentError: the document failed a check :meth:`check_upload`
                does not make, e.g. a PDF with no extractable text. The stored file is
                the caller's to remove.
        """
        data = resolve_stored_path(stored_filename, self._settings).read_bytes()
        source_format = validate_upload(filename, data, self._settings)
        document = self._read_document(data, filename, source_format)
        return self._create_book(
            document,
            data=data,
            filename=filename,
            stored_name=stored_filename,
            source_format=source_format,
            title=title,
            course_id=course_id,
        )

    def _read_document(
        self, data: bytes, filename: str, source_format: SourceFormat
    ) -> BookDocument:
        if source_format is SourceFormat.BOOK_PDF:
            return extract_book_document(data, source_filename=filename)
        return parse_book_document(data)

    def _create_book(
        self,
        document: BookDocument,
        *,
        data: bytes,
        filename: str,
        stored_name: str,
        source_format: SourceFormat,
        title: str | None,
        course_id: int | None,
    ) -> BookRow:
        book = self._books.add(
            BookRow(
                course_id=course_id,
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
            stored_name,
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
