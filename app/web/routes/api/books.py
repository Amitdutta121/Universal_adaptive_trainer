"""Book endpoints: import a book file as chunks, re-import a new version, read, edit, delete.

Import is all-or-nothing. An unreadable file raises before any row is written,
and the error handler renders the reason as JSON (see :mod:`app.errors`). The checks
quick enough to wait for run in the request; parsing a textbook can take minutes,
so the import itself is a background job (ADR-062) the Jobs panel shows. A book's
chunks are read through ``/chunks`` (:mod:`app.web.routes.api.retrieval`).

A YouTube video is a source too (``POST /books/youtube``, Task 30): its transcript is fetched,
or pasted when fetching fails, and stored as timestamped chunks. That runs in the request --
it takes seconds, and a failed fetch has to answer at once so the dialog can offer the paste.

Editing covers the row's labels only -- title, author, notes. The chunks come from
the file, so correcting them means importing a corrected file as a new version.

Deleting refuses by default while questions still cite the book, because their
grounding lives in a frozen spec rather than a foreign key and nothing would
repair it. ``force=true`` is the professor overruling that, with the count in
front of them.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import JobKind, SourceFormat
from app.errors import NotFoundError
from app.ingestion import BookImportService, BookLibraryService
from app.ingestion.storage import resolve_stored_path, store_upload
from app.ingestion.youtube import (
    AvailabilityCheck,
    TranscriptFetch,
    YouTubeImportService,
    check_availability,
    fetch_transcript,
)
from app.jobs.queue import JobQueue, JobQueueDep
from app.jobs.runner import Progress, create_job, execute
from app.persistence.models import BackgroundJobRow
from app.persistence.repositories import BookRepository, ChunkRepository
from app.retrieval.source_embedding import (
    embed_after_import,
    run_source_embedding,
    start_source_embedding,
)
from app.web.routes.api.deps import CourseScope, DbSession, ensure_in_course
from app.web.routes.api.schemas import (
    BookDeletion,
    BookDetail,
    BookImportResult,
    BookListResponse,
    BookMetadataUpdate,
    BookSummary,
    JobStartedResponse,
    YouTubeImportRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=BookListResponse)
def list_books(
    session: DbSession, course: CourseScope, limit: int = 50, usable_only: bool = False
) -> BookListResponse:
    """Every imported book in the course, newest first.

    ``usable_only`` restricts the list to books that have sections to generate
    from, which is what a generation form needs.
    """
    repo = BookRepository(session)
    rows = (
        repo.list_usable(course_id=course)
        if usable_only
        else repo.list_recent(limit=limit, course_id=course)
    )
    return BookListResponse(
        books=[BookSummary.from_row(row) for row in rows],
        total=repo.count(course_id=course),
    )


def _book_in_course(session: Session, book_id: int, course: int | None) -> None:
    ensure_in_course(BookRepository(session).get(book_id).course_id, course, f"Book {book_id}")


@router.post("", response_model=JobStartedResponse, status_code=status.HTTP_202_ACCEPTED)
def import_book(
    session: DbSession,
    course: CourseScope,
    queue: JobQueueDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
) -> JobStartedResponse:
    """Check an uploaded book document, store it, and import it as a background job.

    The type, the size, a JSON document's structure and whether a PDF opens are
    checked here, so the professor still sees those refusals in the import dialog.
    Extracting a PDF's text is :func:`run_book_import`'s, after the ``202``.

    Reading the spooled file synchronously is safe here: the route runs in a
    worker thread, so it does not block the event loop.
    """
    return _start_import(session, course, queue, file, title=title)


def get_youtube_fetch() -> TranscriptFetch:
    """The transcript fetcher; tests override it so no request reaches YouTube."""
    return fetch_transcript


def get_youtube_check() -> AvailabilityCheck:
    """The availability check; tests override it so no request reaches YouTube."""
    return check_availability


@router.post("/youtube", response_model=BookImportResult, status_code=status.HTTP_201_CREATED)
def import_youtube(
    session: DbSession,
    course: CourseScope,
    request: YouTubeImportRequest,
    fetch: Annotated[TranscriptFetch, Depends(get_youtube_fetch)],
    check: Annotated[AvailabilityCheck, Depends(get_youtube_check)],
    queue: JobQueueDep,
) -> BookImportResult:
    """Import a YouTube video's transcript as timestamped chunks; the video is never downloaded.

    A ``422`` with code ``transcript_unavailable`` means the fetch failed and nothing was
    stored: send the same request again with ``transcript`` pasted. The same video again
    returns the source already imported; a different pasted transcript becomes its next version.
    """
    book = YouTubeImportService(session, fetch=fetch, check=check).import_video(
        request.url,
        title=request.title,
        transcript=request.transcript,
        course_id=course,
    )
    session.commit()
    embedding = start_source_embedding(session, book.id)
    if embedding is not None:
        session.commit()
        queue.submit(run_source_embedding, embedding.id)
    return BookImportResult(book=BookSummary.from_row(book))


@router.post(
    "/{book_id}/versions",
    response_model=JobStartedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_book_version(
    session: DbSession,
    course: CourseScope,
    queue: JobQueueDep,
    book_id: int,
    file: Annotated[UploadFile, File()],
) -> JobStartedResponse:
    """Re-import a book's file as its next chunk version, as a background job.

    The same file again changes nothing. A changed one adds a version and makes it
    current; the earlier version's chunks stay, so questions citing them still resolve.
    """
    _book_in_course(session, book_id, course)
    return _start_import(session, course, queue, file, book_id=book_id)


def _start_import(
    session: Session,
    course: int | None,
    queue: JobQueue,
    file: UploadFile,
    *,
    title: str = "",
    book_id: int | None = None,
) -> JobStartedResponse:
    data = file.file.read()
    filename = file.filename or "upload"
    try:
        BookImportService(session).check_upload(filename=filename, data=data)
    except Exception:
        logger.info("Rejected book upload %r", filename)
        raise
    stored_name, _ = store_upload(data, filename, get_settings())
    job = create_job(
        session,
        kind=JobKind.BOOK_IMPORT,
        title=f"Import book · {filename}",
        total=1,
        request={
            "stored_filename": stored_name,
            "filename": filename,
            "title": title,
            "book_id": book_id,
        },
        course_id=course,
    )
    session.commit()
    queue.submit(run_book_import, job.id)
    return JobStartedResponse(job_id=f"job-{job.id}")


def run_book_import(job_id: int, *, session_factory=None) -> None:
    """Background body of ``POST /books``: import the stored upload, record the book, then
    embed its chunks so the first question round does not have to."""
    execute(job_id, _book_import, session_factory=session_factory)
    embed_after_import(job_id, session_factory=session_factory)


def _book_import(session: Session, job: BackgroundJobRow, _progress: Progress) -> dict:
    request = job.request or {}
    stored_filename = request["stored_filename"]
    try:
        book = BookImportService(session).import_stored(
            stored_filename=stored_filename,
            filename=request["filename"],
            title=request.get("title") or "",
            course_id=job.course_id,
            book_id=request.get("book_id"),
        )
        session.commit()
    except Exception:
        # All-or-nothing, as before the import was a job: a refused document leaves
        # neither rows nor its file behind.
        session.rollback()
        resolve_stored_path(stored_filename, get_settings()).unlink(missing_ok=True)
        raise
    # Counted directly, not through ``progress``: that would honour a cancel arriving
    # after the book is already saved. A running import cannot be stopped (jobs route).
    job.done = 1
    return BookImportResult(book=BookSummary.from_row(book)).model_dump(mode="json")


@router.get("/{book_id}", response_model=BookDetail)
def get_book(session: DbSession, course: CourseScope, book_id: int) -> BookDetail:
    """One book: import status, warnings, and how many chunks its current version has."""
    book = BookRepository(session).get(book_id)
    ensure_in_course(book.course_id, course, f"Book {book_id}")
    return BookDetail(
        book=BookSummary.from_row(book),
        chunk_count=ChunkRepository(session).count(book_id),
        current_version=book.current_version,
        warnings=list(book.warnings or []),
        grounded_question_count=BookLibraryService(session).grounded_question_count(book_id),
    )


@router.patch("/{book_id}", response_model=BookSummary)
def update_book(
    session: DbSession, course: CourseScope, book_id: int, update: BookMetadataUpdate
) -> BookSummary:
    """Edit a book's labels. Omitted fields are left as they are."""
    _book_in_course(session, book_id, course)
    book = BookLibraryService(session).update_metadata(
        book_id, title=update.title, author=update.author, notes=update.notes
    )
    session.commit()
    return BookSummary.from_row(book)


@router.delete("/{book_id}", response_model=BookDeletion)
def delete_book(
    session: DbSession, course: CourseScope, book_id: int, force: bool = False
) -> BookDeletion:
    """Delete a book, its chunks and its retained document.

    Refuses with 409 while questions cite the book, naming how many. ``force``
    proceeds anyway; the questions are kept and their citations are stranded.
    """
    _book_in_course(session, book_id, course)
    stranded = BookLibraryService(session).delete(book_id, force=force)
    session.commit()
    return BookDeletion(deleted_book_id=book_id, stranded_question_count=stranded)


@router.get("/{book_id}/source")
def get_book_source(session: DbSession, course: CourseScope, book_id: int) -> FileResponse:
    """The original PDF as uploaded, for in-browser rendering.

    Only a book imported from a PDF (``SourceFormat.BOOK_PDF``) has a source
    file worth serving back -- a DOCX or PPTX (or an old JSON book) has no PDF
    to render, even though it also retains its uploaded file.

    Not a download: no ``filename`` is passed to ``FileResponse``, so no
    ``Content-Disposition: attachment`` header is sent, and a PDF-rendering
    client can fetch it inline.
    """
    book = BookRepository(session).get(book_id)
    ensure_in_course(book.course_id, course, f"Book {book_id}")
    if book.source_format != SourceFormat.BOOK_PDF or not book.stored_filename:
        raise NotFoundError(f"Book {book_id} has no retained PDF source file.")
    settings = get_settings()
    path = resolve_stored_path(book.stored_filename, settings)
    if not path.is_file():
        raise NotFoundError(f"Book {book_id} has no retained PDF source file.")
    return FileResponse(path, media_type="application/pdf")
