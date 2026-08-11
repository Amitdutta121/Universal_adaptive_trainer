"""Server-rendered professor pages.

Each section page is a placeholder that shows real state from the database
(counts, empty lists) plus an explicit note about what is not implemented yet.
Showing genuine empty state rather than mock data keeps the UI honest.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.curriculum import (
    decode_json_list,
    decode_metadata,
    decode_proposal_warnings,
    get_curriculum_proposer,
)
from app.errors import (
    ConfigurationError,
    CurriculumProposalError,
    FileTooLargeError,
    InvalidBookDocumentError,
    LLMRequestError,
    MalformedModelOutputError,
    NotFoundError,
    UnsupportedFileError,
)
from app.ingestion import (
    SCHEMA_VERSION,
    SUPPORTED_EXTENSIONS,
    BookImportService,
    SourceRetrieval,
    decode_warnings,
)
from app.llm import StructuredLLMClient, describe_availability, get_structured_client
from app.persistence.database import get_session
from app.persistence.repositories import (
    BookRepository,
    BookStructureRepository,
    CurriculumRepository,
    ProfessorReviewRepository,
    QuestionRepository,
)
from app.web.templating import render

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])

#: Request-scoped database session.
DbSession = Annotated[Session, Depends(get_session)]


def structured_llm_client() -> StructuredLLMClient | None:
    """The LLM client for this request, or ``None`` when unconfigured.

    Returning ``None`` rather than raising keeps an unconfigured install on the
    Curriculum page with an explanation, instead of bouncing it to a full-page
    error. It is also the seam tests override to run the pipeline against a
    deterministic fake client with no API key present.
    """
    try:
        return get_structured_client()
    except ConfigurationError:
        return None


LLMClient = Annotated[StructuredLLMClient | None, Depends(structured_llm_client)]


@router.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, session: DbSession) -> HTMLResponse:
    """The primary user-facing route."""
    settings = get_settings()
    llm_configured, llm_status = describe_availability(settings)
    counts = {
        "books": BookRepository(session).count(),
        "curriculum": CurriculumRepository(session).count(),
        "questions": QuestionRepository(session).count(),
        "feedback": ProfessorReviewRepository(session).count(),
        "students": 0,
    }
    return render(
        request,
        "index.html",
        {
            "page_title": "Dashboard",
            "active_section": None,
            "counts": counts,
            "llm_configured": llm_configured,
            "llm_status": llm_status,
            "database_url": session.get_bind().url.render_as_string(hide_password=True),
        },
    )


def _books_page(
    request: Request,
    session: Session,
    *,
    error: str | None = None,
    error_detail: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the Books index, optionally with an inline error banner."""
    return render(
        request,
        "books.html",
        {
            "page_title": "Books",
            "active_section": "books",
            "books": BookRepository(session).list_recent(),
            "supported_extensions": SUPPORTED_EXTENSIONS,
            "schema_version": SCHEMA_VERSION,
            "max_upload_mb": get_settings().max_book_upload_mb,
            "error": error,
            "error_detail": error_detail,
        },
        status_code=status_code,
    )


@router.get("/books", response_class=HTMLResponse, name="books")
def books(request: Request, session: DbSession) -> HTMLResponse:
    return _books_page(request, session)


@router.post("/books/upload", name="upload_book")
def upload_book(
    request: Request,
    session: DbSession,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
) -> Response:
    """Import an uploaded book JSON document, then show the book that resulted.

    Every rejection is rendered back onto this page with the reason, because all
    three failure modes -- wrong file type, oversized file, invalid document --
    are things the professor (or their producer script) can fix and retry. Nothing
    is stored unless the document validates in full.
    """
    # Read synchronously from the spooled temp file: this route runs in a worker
    # thread, so reading here does not block the event loop.
    data = file.file.read()
    filename = file.filename or "upload"

    try:
        book = BookImportService(session).import_upload(filename=filename, data=data, title=title)
    except (UnsupportedFileError, FileTooLargeError, InvalidBookDocumentError) as exc:
        session.rollback()
        logger.info("Rejected upload %r: %s", filename, exc.message)
        return _books_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )

    session.commit()
    return RedirectResponse(url=f"/books/{book.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/books/{book_id}", response_class=HTMLResponse, name="book_detail")
def book_detail(request: Request, session: DbSession, book_id: int) -> HTMLResponse:
    """One book: its extraction status, warnings and chapter/section hierarchy."""
    book = BookRepository(session).get_with_structure(book_id)
    retrieval = SourceRetrieval(session)
    return render(
        request,
        "book_detail.html",
        {
            "page_title": book.title,
            "active_section": "books",
            "book": book,
            "chapters": retrieval.chapters_in_book(book_id),
            "warnings": decode_warnings(book.warnings_json),
            "section_count": BookStructureRepository(session).section_count(book_id),
        },
    )


@router.get(
    "/books/{book_id}/sections/{section_id}",
    response_class=HTMLResponse,
    name="book_section",
)
def book_section(
    request: Request, session: DbSession, book_id: int, section_id: int
) -> HTMLResponse:
    """One section: its text plus the source metadata that makes it citable."""
    retrieval = SourceRetrieval(session)
    section = retrieval.get_section(section_id)
    if section.book_id != book_id:
        # The URL asserts a book/section relationship; refuse to render a section
        # under a book it does not belong to rather than show a wrong citation.
        raise NotFoundError(f"Section {section_id} does not belong to book {book_id}.")
    source = retrieval.section_source(section_id)
    return render(
        request,
        "book_section.html",
        {
            "page_title": section.display_title(),
            "active_section": "books",
            "book": BookRepository(session).get(book_id),
            "section": section,
            "source": source,
        },
    )


def _curriculum_page(
    request: Request,
    session: Session,
    *,
    llm_available: bool,
    error: str | None = None,
    error_detail: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the Curriculum index, optionally with an inline error banner."""
    repo = CurriculumRepository(session)
    latest = repo.get_latest()
    return render(
        request,
        "curriculum.html",
        {
            "page_title": "Curriculum",
            "active_section": "curriculum",
            "versions": repo.list_versions(),
            "approved_version": repo.get_approved(),
            "latest_version": repo.get_with_tree(latest.id) if latest else None,
            "book_count": len(BookRepository(session).list_usable()),
            "llm_available": llm_available,
            "llm_status": describe_availability()[1],
            "error": error,
            "error_detail": error_detail,
        },
        status_code=status_code,
    )


@router.get("/curriculum", response_class=HTMLResponse, name="curriculum")
def curriculum(request: Request, session: DbSession, client: LLMClient) -> HTMLResponse:
    return _curriculum_page(request, session, llm_available=client is not None)


@router.post("/curriculum/generate", name="generate_curriculum")
def generate_curriculum(request: Request, session: DbSession, client: LLMClient) -> Response:
    """Derive a proposed Topic -> Subtopic curriculum from the imported books.

    Every failure is rendered back onto this page rather than as a full-page
    error: missing credentials, no books, an unreachable provider and a proposal
    that failed its structural checks are all things the professor can act on and
    retry. Nothing is committed unless the whole proposal passed its checks.
    """
    if client is None:
        return _curriculum_page(
            request,
            session,
            llm_available=False,
            error="Curriculum proposal needs an LLM provider and API key.",
            error_detail=(
                "Set LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in your .env file "
                "(see .env.example), then restart the server."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        version = get_curriculum_proposer(session, client=client).propose()
    except (
        CurriculumProposalError,
        MalformedModelOutputError,
        LLMRequestError,
        ConfigurationError,
    ) as exc:
        session.rollback()
        logger.info("Curriculum proposal failed: %s", exc.message)
        return _curriculum_page(
            request,
            session,
            llm_available=True,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )

    session.commit()
    return RedirectResponse(
        url=f"/curriculum/versions/{version.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get(
    "/curriculum/versions/{version_id}",
    response_class=HTMLResponse,
    name="curriculum_version",
)
def curriculum_version(request: Request, session: DbSession, version_id: int) -> HTMLResponse:
    """One proposal: the Topic -> Subtopic hierarchy with its supporting evidence."""
    repo = CurriculumRepository(session)
    version = repo.get_with_tree(version_id)
    book_ids = decode_json_list(version.source_book_ids_json)
    books = []
    for book_id in book_ids:
        try:
            books.append(BookRepository(session).get(int(book_id)))
        except (NotFoundError, ValueError, TypeError):
            # A book removed after the proposal was made: show what remains
            # rather than failing the page the professor came to review.
            continue
    return render(
        request,
        "curriculum_version.html",
        {
            "page_title": version.label,
            "active_section": "curriculum",
            "version": version,
            "books": books,
            "metadata": decode_metadata(version.extraction_metadata_json),
            "warnings": decode_proposal_warnings(version.warnings_json),
            "subtopic_count": repo.subtopic_count(version_id),
        },
    )


@router.get(
    "/curriculum/subtopics/{subtopic_id}",
    response_class=HTMLResponse,
    name="curriculum_subtopic",
)
def curriculum_subtopic(request: Request, session: DbSession, subtopic_id: int) -> HTMLResponse:
    """One proposed subtopic: definition, sources, evidence and why it was merged."""
    subtopic = CurriculumRepository(session).get_subtopic(subtopic_id)
    evidence = [
        {
            "row": item,
            "quotes": decode_json_list(item.quotes_json),
        }
        for item in subtopic.evidence
    ]
    return render(
        request,
        "curriculum_subtopic.html",
        {
            "page_title": subtopic.name,
            "active_section": "curriculum",
            "subtopic": subtopic,
            "topic": subtopic.topic,
            "version_id": subtopic.topic.curriculum_version_id,
            "candidate_labels": decode_json_list(subtopic.candidate_labels_json),
            "evidence": evidence,
            "book_count": len({item.book_id for item in subtopic.evidence}),
        },
    )


@router.get("/questions", response_class=HTMLResponse, name="questions")
def questions(request: Request, session: DbSession) -> HTMLResponse:
    repo = QuestionRepository(session)
    return render(
        request,
        "questions.html",
        {
            "page_title": "Questions",
            "active_section": "questions",
            "questions": repo.list_recent(),
            "status_counts": repo.count_by_status(),
            "approved_curriculum": CurriculumRepository(session).get_approved(),
        },
    )


@router.get("/feedback", response_class=HTMLResponse, name="feedback")
def feedback(request: Request, session: DbSession) -> HTMLResponse:
    return render(
        request,
        "feedback.html",
        {
            "page_title": "Professor Feedback",
            "active_section": "feedback",
            "reviews": ProfessorReviewRepository(session).list_recent(),
        },
    )


@router.get("/students", response_class=HTMLResponse, name="students")
def students(request: Request) -> HTMLResponse:
    """Students section.

    No student tables exist yet: the adaptive engine is deliberately out of scope
    for this task, so this page documents the fixed mechanism instead of showing
    invented progress data.
    """
    return render(
        request,
        "students.html",
        {"page_title": "Students", "active_section": "students"},
    )
