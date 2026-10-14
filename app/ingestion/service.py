"""The ingestion workflow: validate, then store.

One entry point, :meth:`BookImportService.import_upload`. A JSON upload already
declares its structure, so this only validates and writes the rows. A PDF, DOCX
or PPTX upload is parsed into chunks by :mod:`app.ingestion.parsing`, the source
unit retrieval and generation read (Task 5). A PDF still also gets the
chapter/section tree from :mod:`app.ingestion.pdf` (ADR-048) until everything
reads chunks (Task 10).

Failure handling is deliberate, and everything is checked **before** the first
row is written:

* an unsupported or oversized file is rejected outright;
* a document that fails schema validation, or a file no chunk can be read from,
  is rejected in full -- a half-valid book is never partially imported;
* a document that validates but declares caveats is stored as ``PARTIAL``, never
  as a clean ``IMPORTED``.

Because validation precedes storage, every book row in the database is one whose
structure validated. That is why there is no ``FAILED`` book status.

Chunks are versioned, never rewritten: the same file imported twice is one
import, and a changed file for an existing book becomes its next version.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.enums import BookStatus, SourceFormat
from app.errors import InvalidBookDocumentError
from app.ingestion.parsing import ParsedBook, check_readable, parse_book, resolve_parser
from app.ingestion.pdf import extract_book_document
from app.ingestion.schema import BookDocument, parse_book_document
from app.ingestion.storage import (
    checksum,
    resolve_stored_path,
    store_upload,
    validate_upload,
)
from app.persistence.models import BookChapterRow, BookRow, BookSectionRow, ChunkRow
from app.persistence.repositories import BookRepository, BookStructureRepository, ChunkRepository

logger = logging.getLogger(__name__)


class BookImportService:
    """Imports book files into the source model."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._books = BookRepository(session)
        self._structure = BookStructureRepository(session)
        self._chunks = ChunkRepository(session)
        self._parser = resolve_parser(self._settings.book_parser)

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
            data: the file's bytes -- a UTF-8 JSON book document, a PDF, DOCX or PPTX.
            title: an optional professor-supplied title, which overrides the one
                in the document.
            course_id: the course the book is imported into.

        Returns:
            The persisted book row, in ``IMPORTED`` or ``PARTIAL`` status.

        Raises:
            UnsupportedFileError: the file type is not supported.
            FileTooLargeError: the file exceeds the configured limit.
            InvalidBookDocumentError: the document does not satisfy the schema,
                or the file could not be read.
        """
        source_format = validate_upload(filename, data, self._settings)
        # Validate the structure before storing anything, so a bad document
        # leaves behind neither a file nor a row.
        document, parsed = self._read(data, filename, source_format)
        stored_name, _ = store_upload(data, filename, self._settings)
        return self._create_book(
            document,
            parsed,
            data=data,
            filename=filename,
            stored_name=stored_name,
            source_format=source_format,
            title=title,
            course_id=course_id,
        )

    def check_upload(self, *, filename: str, data: bytes) -> SourceFormat:
        """The checks quick enough to answer while the professor waits.

        Type and size; a JSON document is validated in full (parsing it is cheap), any
        other file is only opened. What remains -- parsing, writing the rows -- is
        :meth:`import_stored`, which a background job runs.

        Raises:
            UnsupportedFileError, FileTooLargeError, InvalidBookDocumentError: as
                :meth:`import_upload`.
        """
        source_format = validate_upload(filename, data, self._settings)
        if source_format is SourceFormat.BOOK_JSON:
            parse_book_document(data)
        else:
            check_readable(data, source_format, self._parser)
        return source_format

    def import_stored(
        self,
        *,
        stored_filename: str,
        filename: str,
        title: str | None = None,
        course_id: int | None = None,
        book_id: int | None = None,
    ) -> BookRow:
        """Import an upload :meth:`check_upload` accepted and the caller already stored.

        The same file twice is one import: a file whose checksum matches a chunked book in
        the course (or the book named by ``book_id``) returns that book unchanged and
        removes the duplicate upload. A changed file for ``book_id`` becomes the book's
        next chunk version; the earlier version's chunks stay, so stored ids still resolve.

        Raises:
            InvalidBookDocumentError: the document failed a check :meth:`check_upload`
                does not make, e.g. a PDF with no extractable text. The stored file is
                the caller's to remove.
        """
        path = resolve_stored_path(stored_filename, self._settings)
        data = path.read_bytes()
        source_format = validate_upload(filename, data, self._settings)

        existing = self._same_file(checksum(data), course_id=course_id, book_id=book_id)
        if existing is not None:
            if existing.stored_filename != stored_filename:
                path.unlink(missing_ok=True)
            logger.info("Upload %s matches book %s; reusing it", filename, existing.id)
            return existing
        if book_id is not None:
            return self._new_version(
                self._books.get(book_id),
                data=data,
                filename=filename,
                stored_name=stored_filename,
                source_format=source_format,
            )

        document, parsed = self._read(data, filename, source_format)
        return self._create_book(
            document,
            parsed,
            data=data,
            filename=filename,
            stored_name=stored_filename,
            source_format=source_format,
            title=title,
            course_id=course_id,
        )

    def _same_file(
        self, digest: str, *, course_id: int | None, book_id: int | None
    ) -> BookRow | None:
        """The chunked book this exact file was already imported as, if any."""
        stmt = select(BookRow).where(
            BookRow.checksum_sha256 == digest, BookRow.current_version.is_not(None)
        )
        stmt = (
            stmt.where(BookRow.id == book_id)
            if book_id is not None
            else stmt.where(BookRow.course_id == course_id)
        )
        return self._session.scalars(stmt.order_by(BookRow.id)).first()

    def _read(
        self, data: bytes, filename: str, source_format: SourceFormat
    ) -> tuple[BookDocument | None, ParsedBook | None]:
        """Everything that can fail, before any row is written.

        A JSON document declares sections only. A PDF still gets the chapter/section tree
        too, until generation reads chunks everywhere (Task 10). DOCX and PPTX get chunks.
        """
        if source_format is SourceFormat.BOOK_JSON:
            return parse_book_document(data), None
        document = (
            extract_book_document(data, source_filename=filename)
            if source_format is SourceFormat.BOOK_PDF
            else None
        )
        parsed = parse_book(
            data, filename=filename, source_format=source_format, parser=self._parser
        )
        return document, parsed

    def _new_version(
        self,
        book: BookRow,
        *,
        data: bytes,
        filename: str,
        stored_name: str,
        source_format: SourceFormat,
    ) -> BookRow:
        """A changed file for an existing book: its next chunk version."""
        if source_format is SourceFormat.BOOK_JSON:
            raise InvalidBookDocumentError(
                "A book JSON document cannot be imported as a new version.",
                detail="Upload the book as a PDF, DOCX or PPTX file.",
            )
        parsed = parse_book(
            data, filename=filename, source_format=source_format, parser=self._parser
        )
        version = self._write_chunks(book, parsed)
        book.original_filename = filename
        book.stored_filename = stored_name
        book.source_format = source_format
        book.file_size_bytes = len(data)
        book.checksum_sha256 = checksum(data)
        book.page_count = parsed.page_count
        book.imported_at = datetime.now(UTC)
        self._session.flush()
        logger.info("Book %s: version %d, %d chunk(s)", book.id, version, len(parsed.chunks))
        return book

    def _write_chunks(self, book: BookRow, parsed: ParsedBook) -> int:
        return self._chunks.add_version(
            book,
            [
                ChunkRow(
                    text=chunk.text,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    heading_path=list(chunk.heading_path),
                )
                for chunk in parsed.chunks
            ],
        )

    def _create_book(
        self,
        document: BookDocument | None,
        parsed: ParsedBook | None,
        *,
        data: bytes,
        filename: str,
        stored_name: str,
        source_format: SourceFormat,
        title: str | None,
        course_id: int | None,
    ) -> BookRow:
        if document is not None:
            declared_title, author, page_count = (
                document.title,
                document.author,
                document.page_count,
            )
        else:
            assert parsed is not None
            declared_title = parsed.title or Path(filename).stem
            author, page_count = parsed.author, parsed.page_count
        book = self._books.add(
            BookRow(
                course_id=course_id,
                title=(title or "").strip() or declared_title,
                author=author,
                original_filename=filename,
                stored_filename=stored_name,
                source_format=source_format,
                file_size_bytes=len(data),
                checksum_sha256=checksum(data),
                source_filename=document.source_filename if document else filename,
                producer=document.producer if document else None,
                page_count=page_count,
                status=BookStatus.PARTIAL
                if document is not None and document.is_partial()
                else BookStatus.IMPORTED,
                warnings=[warning.to_domain() for warning in document.warnings] if document else [],
                imported_at=datetime.now(UTC),
            )
        )
        self._session.flush()
        if document is not None:
            self._persist_structure(book, document)
        if parsed is not None:
            self._write_chunks(book, parsed)

        logger.info(
            "Imported book %s from %s: %d section(s), %d chunk(s), status=%s",
            book.id,
            stored_name,
            document.section_count if document else 0,
            len(parsed.chunks) if parsed else 0,
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
