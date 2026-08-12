"""Book endpoints: import a structured book document and read its structure back.

Import is all-or-nothing. An invalid document raises before any row is written,
and the error handler renders the reason as JSON (see :mod:`app.errors`).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.ingestion import BookImportService, SourceRetrieval
from app.persistence.repositories import BookRepository, BookStructureRepository
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    BookDetail,
    BookListResponse,
    BookSummary,
    ChapterOut,
    SectionDetail,
    SectionListResponse,
    SectionSummary,
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
    )


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
