"""Book endpoints: import a structured book document, read it back, edit, delete.

Import is all-or-nothing. An invalid document raises before any row is written,
and the error handler renders the reason as JSON (see :mod:`app.errors`).

Editing covers the row's labels only -- title, author, notes. Structure is
declared by the imported document (ADR-015), so correcting a chapter means
correcting the document and importing it again, not editing rows here.

Deleting refuses by default while questions still cite the book, because their
grounding lives in a frozen spec rather than a foreign key and nothing would
repair it. ``force=true`` is the professor overruling that, with the count in
front of them.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import SourceFormat
from app.errors import NotFoundError
from app.ingestion import (
    SCHEMA_VERSION,
    STRUCTURE_SOURCE_TERMS,
    SUPPORTED_EXTENSIONS,
    WARNING_CODE_TERMS,
    WARNING_SEVERITY_TERMS,
    BookImportService,
    BookLibraryService,
    SourceRetrieval,
    book_authoring_prompt,
    example_json,
)
from app.ingestion.storage import resolve_stored_path
from app.persistence.repositories import BookRepository, BookStructureRepository
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    BookDeletion,
    BookDetail,
    BookDocumentGuide,
    BookListResponse,
    BookMetadataUpdate,
    BookSummary,
    ChapterOut,
    SectionDetail,
    SectionListResponse,
    SectionSummary,
    VocabularyTermOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=BookListResponse)
def list_books(session: DbSession, limit: int = 50, usable_only: bool = False) -> BookListResponse:
    """Every imported book, newest first.

    ``usable_only`` restricts the list to books that have sections to generate
    from, which is what a generation form needs.
    """
    repo = BookRepository(session)
    rows = repo.list_usable() if usable_only else repo.list_recent(limit=limit)
    return BookListResponse(
        books=[BookSummary.from_row(row) for row in rows],
        total=repo.count(),
    )


@router.post("", response_model=BookSummary, status_code=status.HTTP_201_CREATED)
def import_book(
    session: DbSession,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
) -> BookSummary:
    """Validate and import an uploaded book JSON document.

    Reading the spooled file synchronously is safe here: the route runs in a
    worker thread, so it does not block the event loop.
    """
    data = file.file.read()
    filename = file.filename or "upload"
    try:
        book = BookImportService(session).import_upload(filename=filename, data=data, title=title)
    except Exception:
        session.rollback()
        logger.info("Rejected book upload %r", filename)
        raise
    session.commit()
    return BookSummary.from_row(book)


@router.get("/document-guide", response_model=BookDocumentGuide)
def document_guide() -> BookDocumentGuide:
    """What a valid book document is, and the prompt that produces one.

    Rendered from the ingestion contract rather than written out here, so a
    client cannot describe a document this application would refuse. The prompt
    is advisory: it grants nothing, and every upload is still validated in full.
    """
    settings = get_settings()
    return BookDocumentGuide(
        schema_version=SCHEMA_VERSION,
        supported_extensions=list(SUPPORTED_EXTENSIONS),
        max_upload_mb=settings.max_book_upload_mb,
        prompt=book_authoring_prompt(max_upload_mb=settings.max_book_upload_mb),
        example_json=example_json(),
        structure_sources=VocabularyTermOut.from_terms(STRUCTURE_SOURCE_TERMS),
        warning_codes=VocabularyTermOut.from_terms(WARNING_CODE_TERMS),
        warning_severities=VocabularyTermOut.from_terms(WARNING_SEVERITY_TERMS),
    )


@router.get("/{book_id}", response_model=BookDetail)
def get_book(session: DbSession, book_id: int) -> BookDetail:
    """One book: import status, warnings and its chapter/section hierarchy."""
    book = BookRepository(session).get_with_structure(book_id)
    chapters = SourceRetrieval(session).chapters_in_book(book_id)
    return BookDetail(
        book=BookSummary.from_row(book),
        section_count=BookStructureRepository(session).section_count(book_id),
        chapters=[ChapterOut.from_chapter(chapter) for chapter in chapters],
        warnings=list(book.warnings or []),
        grounded_question_count=BookLibraryService(session).grounded_question_count(book_id),
    )


@router.patch("/{book_id}", response_model=BookSummary)
def update_book(session: DbSession, book_id: int, update: BookMetadataUpdate) -> BookSummary:
    """Edit a book's labels. Omitted fields are left as they are."""
    book = BookLibraryService(session).update_metadata(
        book_id, title=update.title, author=update.author, notes=update.notes
    )
    session.commit()
    return BookSummary.from_row(book)


@router.delete("/{book_id}", response_model=BookDeletion)
def delete_book(session: DbSession, book_id: int, force: bool = False) -> BookDeletion:
    """Delete a book, its structure and its retained document.

    Refuses with 409 while questions cite the book, naming how many. ``force``
    proceeds anyway; the questions are kept and their citations are stranded.
    """
    stranded = BookLibraryService(session).delete(book_id, force=force)
    session.commit()
    return BookDeletion(deleted_book_id=book_id, stranded_question_count=stranded)


@router.get("/{book_id}/source")
def get_book_source(session: DbSession, book_id: int) -> FileResponse:
    """The original PDF as uploaded, for in-browser rendering.

    Only a book imported from a PDF (``SourceFormat.BOOK_PDF``) has a source
    file worth serving back -- a book declared directly as structured JSON has
    no PDF to render, even though it also retains its uploaded file.

    Not a download: no ``filename`` is passed to ``FileResponse``, so no
    ``Content-Disposition: attachment`` header is sent, and a PDF-rendering
    client can fetch it inline.
    """
    book = BookRepository(session).get(book_id)
    if book.source_format != SourceFormat.BOOK_PDF or not book.stored_filename:
        raise NotFoundError(f"Book {book_id} has no retained PDF source file.")
    settings = get_settings()
    path = resolve_stored_path(book.stored_filename, settings)
    if not path.is_file():
        raise NotFoundError(f"Book {book_id} has no retained PDF source file.")
    return FileResponse(path, media_type="application/pdf")


@router.get("/{book_id}/sections", response_model=SectionListResponse)
def list_sections(session: DbSession, book_id: int) -> SectionListResponse:
    """Every section of one book in reading order, without section text."""
    # Confirms the book exists, so an unknown id is a 404 rather than an empty list.
    BookRepository(session).get(book_id)
    sections = SourceRetrieval(session).sections_in_book(book_id)
    return SectionListResponse(
        sections=[SectionSummary.from_section(section) for section in sections],
        total=len(sections),
    )


@router.get("/{book_id}/sections/{section_id}", response_model=SectionDetail)
def get_section(session: DbSession, book_id: int, section_id: int) -> SectionDetail:
    """One section's verbatim text plus the citation that makes it traceable."""
    return _section_detail(session, book_id=book_id, section_id=section_id)


def _section_detail(session: Session, *, book_id: int, section_id: int) -> SectionDetail:
    retrieval = SourceRetrieval(session)
    section = retrieval.get_section(section_id)
    if section.book_id != book_id:
        # The URL asserts a book/section relationship; refuse to serve a section
        # under a book it does not belong to rather than return a wrong citation.
        raise NotFoundError(f"Section {section_id} does not belong to book {book_id}.")
    source = retrieval.section_source(section_id)
    return SectionDetail(
        section=SectionSummary.from_section(section),
        text=section.text,
        warnings=list(section.warnings or []),
        source=source,
        citation=source.citation(),
    )
