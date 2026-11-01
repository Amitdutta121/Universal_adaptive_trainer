"""Parsing an upload into chunks, and versioned re-imports (Task 5).

The suite runs the page-text parser (``BOOK_PARSER=pages`` in conftest); Docling's own
output was checked on the Agah book by hand (``docs/PARSE_SPIKE.md``).
"""

from __future__ import annotations

import io
import zipfile

import pymupdf
import pytest
from book_uploads import finished_job, upload_book
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import SourceFormat
from app.errors import InvalidBookDocumentError, UnsupportedFileError
from app.ingestion import BookImportService
from app.ingestion.parsing import (
    PARSER_DOCLING,
    PARSER_PAGES,
    _heading_path,
    _outline_paths,
    check_readable,
    parse_book,
    resolve_parser,
)
from app.ingestion.storage import store_upload
from app.persistence.models import BookRow, ChunkRow
from app.persistence.repositories import ChunkRepository


def _pdf(*pages: str, toc: list[list] | None = None) -> bytes:
    """One page per argument; each ``|``-separated paragraph is its own text block."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        for slot, paragraph in enumerate(filter(None, text.split("|"))):
            top = 40 + slot * 130
            page.insert_textbox(pymupdf.Rect(40, top, 560, top + 120), paragraph, fontsize=8)
    if toc:
        doc.set_toc(toc)
    data = doc.tobytes()
    doc.close()
    return data


_BOOK = _pdf(
    "Loops repeat a block.|A for loop walks a sequence.",
    "A nested loop is a loop inside another loop.",
    "A function is a named block.",
    toc=[[1, "4. Repetitions", 1], [2, "4.4. Nested Loops", 2], [1, "5. Functions", 3]],
)


# -- outline paths ------------------------------------------------------------


def test_outline_paths_carry_every_level_above() -> None:
    toc = [(1, 1, "4. Loops"), (2, 2, "4.1 For"), (2, 3, "4.2 While"), (1, 5, "5")]
    paths = _outline_paths(toc)
    assert [entry.path for entry in paths] == [
        ("4. Loops",),
        ("4. Loops", "4.1 For"),
        ("4. Loops", "4.2 While"),
        ("5",),
    ]


def test_a_chunk_heading_is_matched_to_the_outline_else_placed_by_page() -> None:
    paths = _outline_paths([(1, 1, "4. Loops"), (2, 2, "4.4. Nested Loops"), (1, 5, "5. Fns")])
    assert _heading_path(paths, ["4.4.  nested loops"], 2) == ("4. Loops", "4.4. Nested Loops")
    assert _heading_path(paths, ["Something else"], 6) == ("5. Fns",)
    assert _heading_path([], ["Docling heading"], 1) == ("Docling heading",)


# -- parsing --------------------------------------------------------------------


def test_every_chunk_has_a_page_range_and_a_heading_path() -> None:
    parsed = parse_book(
        _BOOK, filename="book.pdf", source_format=SourceFormat.BOOK_PDF, parser=PARSER_PAGES
    )

    assert parsed.page_count == 3
    assert [chunk.page_start for chunk in parsed.chunks] == [1, 2, 3]
    assert all(chunk.page_end == chunk.page_start for chunk in parsed.chunks)
    assert [chunk.heading_path for chunk in parsed.chunks] == [
        ("4. Repetitions",),
        ("4. Repetitions", "4.4. Nested Loops"),
        ("5. Functions",),
    ]
    assert "for loop" in parsed.chunks[0].text


def test_a_long_page_is_split_at_paragraphs() -> None:
    paragraph = "word " * 100
    data = _pdf("|".join([paragraph] * 5))
    parsed = parse_book(
        data, filename="b.pdf", source_format=SourceFormat.BOOK_PDF, parser=PARSER_PAGES
    )
    assert len(parsed.chunks) > 1
    assert all(len(chunk.text) <= 1200 for chunk in parsed.chunks)


def test_a_pdf_with_no_text_is_refused() -> None:
    with pytest.raises(InvalidBookDocumentError):
        parse_book(
            _pdf("", ""),
            filename="blank.pdf",
            source_format=SourceFormat.BOOK_PDF,
            parser=PARSER_PAGES,
        )


def test_office_files_need_docling() -> None:
    with pytest.raises(UnsupportedFileError):
        check_readable(b"PK", SourceFormat.BOOK_DOCX, PARSER_PAGES)


def test_an_office_file_that_is_not_one_is_refused_before_parsing() -> None:
    with pytest.raises(InvalidBookDocumentError):
        check_readable(b"not a zip", SourceFormat.BOOK_DOCX, PARSER_DOCLING)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("word/other.xml", "")
    with pytest.raises(InvalidBookDocumentError):
        check_readable(archive.getvalue(), SourceFormat.BOOK_PPTX, PARSER_DOCLING)


def test_the_pages_setting_never_runs_docling() -> None:
    assert resolve_parser("pages") == PARSER_PAGES


# -- import and versions ----------------------------------------------------------


def _import(service: BookImportService, settings: Settings, data: bytes, **kwargs) -> BookRow:
    stored, _ = store_upload(data, "book.pdf", settings)
    return service.import_stored(stored_filename=stored, filename="book.pdf", **kwargs)


def test_a_pdf_import_writes_version_one(session: Session, settings: Settings) -> None:
    book = _import(BookImportService(session, settings), settings, _BOOK, course_id=None)

    assert book.current_version == 1
    chunks = ChunkRepository(session).list_for_book(book.id)
    assert len(chunks) == 3
    assert all(chunk.page_start is not None and chunk.heading_path for chunk in chunks)


def test_the_same_file_twice_reuses_the_book_and_its_version(
    session: Session, settings: Settings
) -> None:
    service = BookImportService(session, settings)
    first = _import(service, settings, _BOOK)
    ids = [chunk.id for chunk in ChunkRepository(session).list_for_book(first.id)]

    again = _import(service, settings, _BOOK)
    same_book = _import(service, settings, _BOOK, book_id=first.id)

    assert again.id == first.id == same_book.id
    assert first.current_version == 1
    assert [chunk.id for chunk in ChunkRepository(session).list_for_book(first.id)] == ids
    assert session.query(BookRow).count() == 1
    assert len(list(settings.book_upload_dir.iterdir())) == 1


def test_a_changed_file_becomes_the_next_version(session: Session, settings: Settings) -> None:
    service = BookImportService(session, settings)
    book = _import(service, settings, _BOOK)
    old_ids = [chunk.id for chunk in ChunkRepository(session).list_for_book(book.id)]

    changed = _pdf("Loops repeat a block, now with more words.", toc=[[1, "4. Loops", 1]])
    _import(service, settings, changed, book_id=book.id)

    assert book.current_version == 2
    current = ChunkRepository(session).list_for_book(book.id)
    assert [chunk.heading_path for chunk in current] == [["4. Loops"]]
    assert all(ChunkRepository(session).get(chunk_id) for chunk_id in old_ids)


def test_a_corrupt_file_writes_no_rows(session: Session, settings: Settings) -> None:
    with pytest.raises(InvalidBookDocumentError):
        BookImportService(session, settings).import_upload(
            filename="book.pdf", data=b"%PDF-1.4 broken"
        )
    assert session.query(BookRow).count() == 0
    assert session.query(ChunkRow).count() == 0


def test_the_version_endpoint_adds_a_version(client: TestClient) -> None:
    book = upload_book(client, files={"file": ("book.pdf", _BOOK, "application/pdf")})
    changed = _pdf("A different first page.")

    response = client.post(
        f"/api/books/{book['id']}/versions",
        files={"file": ("book-v2.pdf", changed, "application/pdf")},
    )

    assert response.status_code == 202, response.text
    job = finished_job(client, response.json()["job_id"])
    assert job["status"] == "done", job
    assert job["result"]["book"]["id"] == book["id"]


def test_docling_uses_the_downloaded_models_and_fetches_them_otherwise(
    tmp_path, monkeypatch
) -> None:
    """``models/docling`` filled by ``scripts.download_docling_models`` keeps PDF parsing off
    the Hugging Face Hub; an empty or missing folder leaves Docling to fetch them itself."""
    from types import SimpleNamespace

    from app.ingestion import parsing

    folder = tmp_path / "docling"
    monkeypatch.setattr(
        parsing, "get_settings", lambda: SimpleNamespace(docling_artifacts_path=folder)
    )
    assert parsing._docling_artifacts() is None
    folder.mkdir()
    assert parsing._docling_artifacts() is None
    (folder / "docling-project--docling-layout-heron").mkdir()
    assert parsing._docling_artifacts() == str(folder)
