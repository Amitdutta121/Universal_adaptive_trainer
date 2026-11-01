"""The import workflow: validation, retention, chunking and status.

Versions and same-file reuse are in ``tests/test_ingestion_chunking.py``.
"""

from __future__ import annotations

import book_documents as docs
import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import BookStatus, SourceFormat
from app.errors import FileTooLargeError, InvalidBookDocumentError, UnsupportedFileError
from app.ingestion import BookImportService, format_for_filename, validate_upload
from app.ingestion.storage import resolve_stored_path, safe_filename
from app.persistence.models import BookRow, ChunkRow
from app.persistence.repositories import BookRepository, ChunkRepository


@pytest.fixture
def service(session: Session, settings: Settings) -> BookImportService:
    return BookImportService(session, settings)


class TestUploadValidation:
    def test_accepts_pdf_docx_and_pptx(self) -> None:
        assert format_for_filename("BOOK.PDF") is SourceFormat.BOOK_PDF
        assert format_for_filename("book.docx") is SourceFormat.BOOK_DOCX
        assert format_for_filename("book.pptx") is SourceFormat.BOOK_PPTX

    @pytest.mark.parametrize("filename", ["book.odt", "book.exe", "book"])
    def test_rejects_unsupported_extensions(self, filename: str) -> None:
        with pytest.raises(UnsupportedFileError):
            format_for_filename(filename)

    @pytest.mark.parametrize("filename", ["book.json", "book.md", "book.txt", "book.epub"])
    def test_other_book_formats_are_told_what_to_supply(self, filename: str) -> None:
        """Including the retired book JSON document: the message says what is wanted."""
        with pytest.raises(UnsupportedFileError) as exc:
            format_for_filename(filename)
        assert "cannot be imported directly" in exc.value.message
        assert "PDF, DOCX or PPTX" in (exc.value.detail or "")

    def test_rejects_an_empty_file(self, settings: Settings) -> None:
        with pytest.raises(UnsupportedFileError):
            validate_upload("book.pdf", b"", settings)

    def test_rejects_an_oversized_file(self, settings: Settings) -> None:
        oversized = b"x" * (settings.max_book_upload_mb * 1024 * 1024 + 1)
        with pytest.raises(FileTooLargeError):
            validate_upload("book.pdf", oversized, settings)


class TestSafeFilename:
    def test_keeps_the_original_name_visible(self) -> None:
        assert safe_filename("Think Python.pdf").endswith("_Think_Python.pdf")

    def test_two_uploads_of_the_same_name_do_not_collide(self) -> None:
        assert safe_filename("book.pdf") != safe_filename("book.pdf")

    def test_strips_path_traversal(self) -> None:
        stored = safe_filename("../../etc/passwd")
        assert ".." not in stored
        assert "/" not in stored and "\\" not in stored


class TestSuccessfulImport:
    @pytest.fixture
    def data(self) -> bytes:
        return docs.to_pdf(docs.think_python())

    @pytest.fixture
    def book(self, service: BookImportService, session: Session, data: bytes) -> BookRow:
        row = service.import_upload(filename="think_python.pdf", data=data)
        session.commit()
        return row

    def test_status_is_imported(self, book: BookRow) -> None:
        assert book.status == BookStatus.IMPORTED

    def test_title_and_author_come_from_the_file(self, book: BookRow) -> None:
        assert book.title == "Think Python"
        assert book.author == "Allen B. Downey"

    def test_records_provenance(self, book: BookRow) -> None:
        assert book.original_filename == "think_python.pdf"
        assert book.source_format is SourceFormat.BOOK_PDF
        assert book.producer == "pages parser"
        assert book.checksum_sha256 and len(book.checksum_sha256) == 64

    def test_retains_the_uploaded_file(
        self, book: BookRow, settings: Settings, data: bytes
    ) -> None:
        """The exact input is kept, so an import is reproducible from it."""
        assert resolve_stored_path(book.stored_filename, settings).read_bytes() == data

    def test_writes_version_one_with_pages_and_heading_paths(
        self, book: BookRow, session: Session
    ) -> None:
        chunks = ChunkRepository(session).list_for_book(book.id)
        assert book.current_version == 1
        assert [chunk.page_start for chunk in chunks] == [1, 2, 3, 4]
        assert chunks[0].heading_path == ["1 The Way of the Program", "1.1 What Is a Program?"]
        assert chunks[0].text == "A program is a sequence of instructions."

    def test_page_count_is_stored(self, book: BookRow) -> None:
        assert book.page_count == 4

    def test_professor_supplied_title_wins(
        self, service: BookImportService, session: Session, data: bytes
    ) -> None:
        row = service.import_upload(filename="b.pdf", data=data, title="  CS 135 Reader  ")
        assert row.title == "CS 135 Reader"

    def test_a_pdf_without_a_title_is_named_after_its_file(
        self, service: BookImportService
    ) -> None:
        untitled = docs.to_pdf({**docs.minimal(), "title": ""})
        assert service.import_upload(filename="reader.pdf", data=untitled).title == "reader"


class TestRejectedImport:
    """Nothing is stored unless the file reads into at least one chunk."""

    def test_a_pdf_with_no_text_stores_no_book_and_no_file(
        self, service: BookImportService, session: Session, settings: Settings
    ) -> None:
        blank = docs.to_pdf({"title": "Blank", "chapters": [{"sections": [{"text": ""}]}]})
        with pytest.raises(InvalidBookDocumentError):
            service.import_upload(filename="blank.pdf", data=blank)
        assert BookRepository(session).count() == 0
        assert session.query(ChunkRow).count() == 0
        upload_dir = settings.book_upload_dir
        assert not upload_dir.exists() or not list(upload_dir.iterdir())

    def test_an_unsupported_type_creates_no_book(
        self, service: BookImportService, session: Session
    ) -> None:
        with pytest.raises(UnsupportedFileError):
            service.import_upload(filename="book.json", data=b"{}")
        assert BookRepository(session).count() == 0

    def test_an_unreadable_pdf_creates_no_book(
        self, service: BookImportService, session: Session
    ) -> None:
        with pytest.raises(InvalidBookDocumentError):
            service.import_upload(filename="book.pdf", data=b"%PDF-1.4\nnot a real pdf")
        assert BookRepository(session).count() == 0
