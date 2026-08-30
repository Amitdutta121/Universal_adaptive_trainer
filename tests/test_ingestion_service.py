"""The import workflow: validation, retention, persistence and status."""

from __future__ import annotations

import book_documents as docs
import pymupdf
import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import BookStatus, SourceFormat, StructureConfidence, StructureSource
from app.errors import FileTooLargeError, InvalidBookDocumentError, UnsupportedFileError
from app.ingestion import (
    BookImportService,
    format_for_filename,
    parse_book_document,
    validate_upload,
)
from app.ingestion.storage import resolve_stored_path, safe_filename
from app.persistence.models import BookRow
from app.persistence.repositories import BookRepository, BookStructureRepository


@pytest.fixture
def service(session: Session, settings: Settings) -> BookImportService:
    return BookImportService(session, settings)


def _one_page_pdf(text: str) -> bytes:
    """A tiny, real PDF with no embedded outline, for exercising the fallback path."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


class TestUploadValidation:
    def test_accepts_json(self) -> None:
        assert format_for_filename("book.json") is SourceFormat.BOOK_JSON
        assert format_for_filename("BOOK.JSON") is SourceFormat.BOOK_JSON

    def test_accepts_pdf(self) -> None:
        assert format_for_filename("book.pdf") is SourceFormat.BOOK_PDF
        assert format_for_filename("BOOK.PDF") is SourceFormat.BOOK_PDF

    @pytest.mark.parametrize("filename", ["book.docx", "book.exe", "book"])
    def test_rejects_unsupported_extensions(self, filename: str) -> None:
        with pytest.raises(UnsupportedFileError):
            format_for_filename(filename)

    @pytest.mark.parametrize("filename", ["book.md", "book.txt", "book.epub"])
    def test_raw_book_formats_are_told_what_to_supply(self, filename: str) -> None:
        """A raw book file this application still does not convert is not silently
        refused: the message says what is wanted instead."""
        with pytest.raises(UnsupportedFileError) as exc:
            format_for_filename(filename)
        assert "cannot be imported directly" in exc.value.message
        assert "structured book JSON" in (exc.value.detail or "")

    def test_rejects_an_empty_file(self, settings: Settings) -> None:
        with pytest.raises(UnsupportedFileError):
            validate_upload("book.json", b"", settings)

    def test_rejects_an_oversized_file(self, settings: Settings) -> None:
        oversized = b"x" * (settings.max_book_upload_mb * 1024 * 1024 + 1)
        with pytest.raises(FileTooLargeError):
            validate_upload("book.json", oversized, settings)


class TestSafeFilename:
    def test_keeps_the_original_name_visible(self) -> None:
        assert safe_filename("Think Python.json").endswith("_Think_Python.json")

    def test_two_uploads_of_the_same_name_do_not_collide(self) -> None:
        assert safe_filename("book.json") != safe_filename("book.json")

    def test_strips_path_traversal(self) -> None:
        stored = safe_filename("../../etc/passwd")
        assert ".." not in stored
        assert "/" not in stored and "\\" not in stored


class TestSuccessfulImport:
    @pytest.fixture
    def book(self, service: BookImportService, session: Session) -> BookRow:
        row = service.import_upload(
            filename="think_python.json", data=docs.to_bytes(docs.think_python())
        )
        session.commit()
        return row

    def test_status_is_imported(self, book: BookRow) -> None:
        assert book.status == BookStatus.IMPORTED

    def test_title_and_author_come_from_the_document(self, book: BookRow) -> None:
        assert book.title == "Think Python"
        assert book.author == "Allen B. Downey"

    def test_records_provenance(self, book: BookRow) -> None:
        assert book.original_filename == "think_python.json"
        assert book.source_filename == "think_python.pdf"
        assert book.producer == "example-converter 1.0"
        assert book.checksum_sha256 and len(book.checksum_sha256) == 64

    def test_retains_the_uploaded_document(self, book: BookRow, settings: Settings) -> None:
        """The exact input is kept, so an import is reproducible from it."""
        stored = resolve_stored_path(book.stored_filename, settings)
        assert stored.exists()
        assert parse_book_document(stored.read_bytes()).title == "Think Python"

    def test_persists_the_chapter_and_section_tree(self, book: BookRow, session: Session) -> None:
        structure = BookStructureRepository(session)
        chapters = structure.chapters_in_book(book.id)
        assert [chapter.number for chapter in chapters] == ["1", "2"]
        assert [chapter.title for chapter in chapters] == [
            "The Way of the Program",
            "Variables, Expressions and Statements",
        ]
        assert [section.number for section in structure.sections_in_book(book.id)] == [
            "1.1",
            "1.2",
            "2.1",
            "2.2",
        ]

    def test_persists_section_text_and_pages(self, book: BookRow, session: Session) -> None:
        first = BookStructureRepository(session).sections_in_book(book.id)[0]
        assert first.text == "A program is a sequence of instructions."
        assert first.char_count == len(first.text)
        assert first.start_page == 17
        assert first.end_page == 18

    def test_persists_declared_confidence(self, book: BookRow, session: Session) -> None:
        first = BookStructureRepository(session).sections_in_book(book.id)[0]
        assert first.structure_confidence == StructureConfidence.HIGH

    def test_page_count_is_stored(self, book: BookRow) -> None:
        assert book.page_count == 292

    def test_professor_supplied_title_wins(
        self, service: BookImportService, session: Session
    ) -> None:
        book = service.import_upload(
            filename="think_python.json",
            data=docs.to_bytes(docs.think_python()),
            title="My Course Reader",
        )
        session.commit()
        assert book.title == "My Course Reader"


class TestCaveatedImport:
    def test_a_document_declaring_defects_is_partial(
        self, service: BookImportService, session: Session
    ) -> None:
        book = service.import_upload(
            filename="uncertain.json", data=docs.to_bytes(docs.with_caveats())
        )
        session.commit()
        assert book.status == BookStatus.PARTIAL

    def test_declared_warnings_are_stored_and_readable(
        self, service: BookImportService, session: Session
    ) -> None:
        book = service.import_upload(
            filename="uncertain.json", data=docs.to_bytes(docs.with_caveats())
        )
        session.commit()
        warnings = book.warnings
        assert [warning.code for warning in warnings] == ["producer_inferred_structure"]

    def test_guessed_boundaries_are_stored_as_low_confidence(
        self, service: BookImportService, session: Session
    ) -> None:
        book = service.import_upload(
            filename="uncertain.json", data=docs.to_bytes(docs.with_caveats())
        )
        session.commit()
        section = BookStructureRepository(session).sections_in_book(book.id)[0]
        assert section.structure_confidence == StructureConfidence.LOW

    def test_informational_warnings_leave_the_book_clean(
        self, service: BookImportService, session: Session
    ) -> None:
        book = service.import_upload(
            filename="clean.json", data=docs.to_bytes(docs.informational_only())
        )
        session.commit()
        assert book.status == BookStatus.IMPORTED
        assert book.warnings

    def test_partial_books_are_still_usable_for_grounding(
        self, service: BookImportService, session: Session
    ) -> None:
        service.import_upload(filename="uncertain.json", data=docs.to_bytes(docs.with_caveats()))
        session.commit()
        assert len(BookRepository(session).list_usable()) == 1


class TestPdfImport:
    """A PDF upload goes through extraction (ADR-048), then the same workflow."""

    def test_a_pdf_with_a_detectable_heading_imports_as_partial(
        self, service: BookImportService, session: Session
    ) -> None:
        data = _one_page_pdf("Chapter 1\nThis is the only section text of a tiny test book.")
        book = service.import_upload(filename="tiny.pdf", data=data)
        session.commit()

        assert book.source_format is SourceFormat.BOOK_PDF
        # No embedded outline, so the regex fallback ran and the book is
        # honestly marked partial rather than presented as declared structure.
        assert book.status == BookStatus.PARTIAL

        section = BookStructureRepository(session).sections_in_book(book.id)[0]
        assert section.structure_source is StructureSource.PRODUCER_INFERRED
        assert "tiny test book" in section.text

    def test_the_original_pdf_bytes_are_retained(
        self, service: BookImportService, session: Session, settings: Settings
    ) -> None:
        data = _one_page_pdf("Chapter 1\nBody text.")
        book = service.import_upload(filename="tiny.pdf", data=data)
        session.commit()

        stored = resolve_stored_path(book.stored_filename, settings)
        assert stored.read_bytes() == data


class TestRejectedImport:
    """Nothing is stored unless the document validates in full."""

    def test_an_invalid_document_creates_no_book(
        self, service: BookImportService, session: Session
    ) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["text"] = ""
        with pytest.raises(InvalidBookDocumentError):
            service.import_upload(filename="bad.json", data=docs.to_bytes(document))
        assert BookRepository(session).count() == 0

    def test_an_invalid_document_stores_no_file(
        self, service: BookImportService, settings: Settings
    ) -> None:
        with pytest.raises(InvalidBookDocumentError):
            service.import_upload(filename="bad.json", data=b"{not json")
        upload_dir = settings.book_upload_dir
        assert not upload_dir.exists() or not list(upload_dir.iterdir())

    def test_an_unsupported_type_creates_no_book(
        self, service: BookImportService, session: Session
    ) -> None:
        with pytest.raises(UnsupportedFileError):
            service.import_upload(filename="book.docx", data=b"whatever")
        assert BookRepository(session).count() == 0

    def test_an_unreadable_pdf_creates_no_book(
        self, service: BookImportService, session: Session
    ) -> None:
        with pytest.raises(InvalidBookDocumentError):
            service.import_upload(filename="book.pdf", data=b"%PDF-1.4\nnot a real pdf")
        assert BookRepository(session).count() == 0


class TestReImport:
    def test_replacing_a_structure_does_not_duplicate_sections(
        self, service: BookImportService, session: Session
    ) -> None:
        """Re-importing a corrected document replaces rather than accumulates."""
        book = service.import_upload(filename="think.json", data=docs.to_bytes(docs.think_python()))
        session.commit()
        assert BookStructureRepository(session).section_count(book.id) == 4

        service.replace_structure(book, parse_book_document(docs.to_bytes(docs.think_python())))
        session.commit()
        assert BookStructureRepository(session).section_count(book.id) == 4

    def test_re_import_keeps_the_book_id(
        self, service: BookImportService, session: Session
    ) -> None:
        book = service.import_upload(filename="think.json", data=docs.to_bytes(docs.think_python()))
        session.commit()
        original_id = book.id

        service.replace_structure(book, parse_book_document(docs.to_bytes(docs.minimal())))
        session.commit()
        assert book.id == original_id
        assert book.title == "Tiny Book"
        assert BookStructureRepository(session).section_count(book.id) == 1
