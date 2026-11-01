"""The ingestion workflow: check, parse into chunks, store.

One entry point for a waiting professor, :meth:`BookImportService.check_upload`, and one
for the background import job, :meth:`BookImportService.import_stored`.
:meth:`BookImportService.import_upload` does both in one call (scripts and tests). A PDF,
DOCX or PPTX is parsed into chunks by :mod:`app.ingestion.parsing`, the one source unit
retrieval, generation and citations read (``tasks/plan.md``, Phase 1).

Failure handling is deliberate, and everything is checked **before** the first row is
written: an unsupported, oversized or unreadable file, or one no chunk can be read from,
is rejected in full. A half-imported book is never stored.

Chunks are versioned, never rewritten: the same file imported twice is one import, and a
changed file for an existing book becomes its next version.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.enums import BookStatus, SourceFormat
from app.ingestion.parsing import ParsedBook, check_readable, parse_book, resolve_parser
from app.ingestion.storage import (
    checksum,
    resolve_stored_path,
    store_upload,
    validate_upload,
)
from app.persistence.models import BookRow, ChunkRow
from app.persistence.repositories import BookRepository, ChunkRepository

logger = logging.getLogger(__name__)


class BookImportService:
    """Imports book files as chunked books."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._books = BookRepository(session)
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
        """Check, parse and store one uploaded book file in a single call.

        Args:
            filename: the name the professor's browser supplied.
            data: the file's bytes -- a PDF, DOCX or PPTX.
            title: an optional professor-supplied title, which overrides the file's own.
            course_id: the course the book is imported into.

        Raises:
            UnsupportedFileError: the file type is not supported.
            FileTooLargeError: the file exceeds the configured limit.
            InvalidBookDocumentError: the file could not be read, or held no text.
        """
        source_format = validate_upload(filename, data, self._settings)
        # Parsed before storing anything, so a bad file leaves neither a file nor a row.
        parsed = self._parse(data, filename, source_format)
        stored_name, _ = store_upload(data, filename, self._settings)
        return self._create_book(
            parsed,
            data=data,
            filename=filename,
            stored_name=stored_name,
            source_format=source_format,
            title=title,
            course_id=course_id,
        )

    def check_upload(self, *, filename: str, data: bytes) -> SourceFormat:
        """The checks quick enough to answer while the professor waits: type, size, opens.

        Parsing and writing the rows is :meth:`import_stored`, which a background job runs.

        Raises:
            UnsupportedFileError, FileTooLargeError, InvalidBookDocumentError: as
                :meth:`import_upload`.
        """
        source_format = validate_upload(filename, data, self._settings)
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
            InvalidBookDocumentError: the file failed a check :meth:`check_upload` does not
                make, e.g. a PDF with no extractable text. The stored file is the caller's
                to remove.
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

        parsed = self._parse(data, filename, source_format)
        if book_id is not None:
            return self._new_version(
                self._books.get(book_id),
                parsed,
                data=data,
                filename=filename,
                stored_name=stored_filename,
                source_format=source_format,
            )
        return self._create_book(
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

    def _parse(self, data: bytes, filename: str, source_format: SourceFormat) -> ParsedBook:
        return parse_book(data, filename=filename, source_format=source_format, parser=self._parser)

    def _new_version(
        self,
        book: BookRow,
        parsed: ParsedBook,
        *,
        data: bytes,
        filename: str,
        stored_name: str,
        source_format: SourceFormat,
    ) -> BookRow:
        """A changed file for an existing book: its next chunk version."""
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
        parsed: ParsedBook,
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
                title=(title or "").strip() or parsed.title or Path(filename).stem,
                author=parsed.author,
                original_filename=filename,
                stored_filename=stored_name,
                source_format=source_format,
                file_size_bytes=len(data),
                checksum_sha256=checksum(data),
                source_filename=filename,
                producer=f"{parsed.parser} parser",
                page_count=parsed.page_count,
                status=BookStatus.IMPORTED,
                imported_at=datetime.now(UTC),
            )
        )
        self._session.flush()
        self._write_chunks(book, parsed)
        logger.info(
            "Imported book %s from %s: %d chunk(s) by %s",
            book.id,
            stored_name,
            len(parsed.chunks),
            parsed.parser,
        )
        return book
