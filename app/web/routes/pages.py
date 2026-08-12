"""Server-rendered professor pages.

These routes render HTML; they do not implement behaviour. Every action a page
submits is delegated to the matching handler in :mod:`app.web.routes.api`, which
is the single implementation of that capability (ADR-027). A page's own work is
limited to choosing a template, passing display objects to it, and turning a
raised :class:`~app.errors.AdaptiveTrainerError` into an inline banner instead of
a full error page.

Read paths still pass ORM rows and domain objects to Jinja, because the
templates call methods on them (``display_title()``, ``citation()``) that the
API's JSON schemas deliberately do not carry.
"""

from __future__ import annotations

import logging
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.calibration import MIN_INFORMATIVE_SAMPLE
from app.config import get_settings
from app.curriculum import extraction_metadata, proposal_warnings
from app.curriculum.taxonomy_schema import SCHEMA_VERSION as TAXONOMY_SCHEMA_VERSION
from app.domain.enums import Difficulty, QuestionType, RejectionReason, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS
from app.errors import (
    ConfigurationError,
    DomainRuleError,
    FileTooLargeError,
    InvalidBookDocumentError,
    InvalidQuestionSpecError,
    InvalidTaxonomyDocumentError,
    LLMRequestError,
    MalformedModelOutputError,
    NotFoundError,
    UnsupportedFileError,
)
from app.ingestion import SCHEMA_VERSION, SUPPORTED_EXTENSIONS, SourceRetrieval
from app.llm import describe_availability
from app.persistence.database import get_session
from app.persistence.repositories import (
    BookRepository,
    BookStructureRepository,
    CurriculumRepository,
    QuestionRepository,
)
from app.web.routes.api import books as api_books
from app.web.routes.api import calibration as api_calibration
from app.web.routes.api import curriculum as api_curriculum
from app.web.routes.api import evaluation as api_evaluation
from app.web.routes.api import feedback as api_feedback
from app.web.routes.api import preferences as api_preferences
from app.web.routes.api import questions as api_questions
from app.web.routes.api import system as api_system
from app.web.routes.api.schemas import (
    CorrectPreferenceRequest,
    GenerateQuestionsRequest,
    ReviewRequest,
)
from app.web.templating import render

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])

#: Request-scoped database session.
DbSession = Annotated[Session, Depends(get_session)]


@router.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, session: DbSession) -> HTMLResponse:
    """The primary user-facing route."""
    settings = get_settings()
    llm_configured, llm_status = describe_availability(settings)
    totals = api_system.counts(session)
    counts = {
        "books": totals.books,
        "curriculum": totals.curriculum_versions,
        "questions": totals.questions,
        "feedback": totals.reviews,
        "preferences": totals.preferences,
        "students": totals.students,
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
    try:
        book = api_books.import_book(session, file, title)
    except (UnsupportedFileError, FileTooLargeError, InvalidBookDocumentError) as exc:
        logger.info("Rejected upload %r: %s", file.filename, exc.message)
        return _books_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
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
            "warnings": book.warnings,
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
            "schema_version": TAXONOMY_SCHEMA_VERSION,
            "format_hint": "schema_version, label, topics, and each topic's subtopics",
            "error": error,
            "error_detail": error_detail,
        },
        status_code=status_code,
    )


@router.get("/curriculum", response_class=HTMLResponse, name="curriculum")
def curriculum(request: Request, session: DbSession) -> HTMLResponse:
    return _curriculum_page(request, session)


@router.post("/curriculum/upload", name="upload_taxonomy")
def upload_taxonomy(
    request: Request,
    session: DbSession,
    file: Annotated[UploadFile, File()],
) -> Response:
    """Import an uploaded fixed taxonomy and open its approved version."""
    try:
        imported = api_curriculum.import_taxonomy(session, file)
    except (UnsupportedFileError, FileTooLargeError, InvalidTaxonomyDocumentError) as exc:
        logger.info("Rejected taxonomy upload %r: %s", file.filename, exc.message)
        return _curriculum_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
    return RedirectResponse(
        url=f"/curriculum/versions/{imported.version.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get(
    "/curriculum/versions/{version_id}",
    response_class=HTMLResponse,
    name="curriculum_version",
)
def curriculum_version(request: Request, session: DbSession, version_id: int) -> HTMLResponse:
    """One curriculum version: the Topic -> Subtopic hierarchy."""
    repo = CurriculumRepository(session)
    version = repo.get_with_tree(version_id)
    book_ids = version.source_book_ids
    books = []
    for book_id in book_ids:
        try:
            books.append(BookRepository(session).get(int(book_id)))
        except (NotFoundError, ValueError, TypeError):
            # A book removed after a legacy version was created: show what remains
            # rather than failing the page the professor came to inspect.
            continue
    return render(
        request,
        "curriculum_version.html",
        {
            "page_title": version.label,
            "active_section": "curriculum",
            "version": version,
            "books": books,
            "metadata": extraction_metadata(version.extraction_metadata),
            "warnings": proposal_warnings(version.warnings),
            "subtopic_count": repo.subtopic_count(version_id),
        },
    )


@router.get(
    "/curriculum/subtopics/{subtopic_id}",
    response_class=HTMLResponse,
    name="curriculum_subtopic",
)
def curriculum_subtopic(request: Request, session: DbSession, subtopic_id: int) -> HTMLResponse:
    """One subtopic: definition and, for legacy rows, textbook evidence."""
    subtopic = CurriculumRepository(session).get_subtopic(subtopic_id)
    evidence = [
        {
            "row": item,
            "quotes": item.quotes,
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
            "is_taxonomy_upload": (
                subtopic.topic.curriculum_version.generated_by == "taxonomy-upload"
            ),
            "candidate_labels": subtopic.candidate_labels,
            "evidence": evidence,
            "book_count": len({item.book_id for item in subtopic.evidence}),
        },
    )


def _questions_page(
    request: Request,
    session: Session,
    *,
    selected_book_id: int | None = None,
    created_count: int | None = None,
    created_ids: list[int] | None = None,
    judge_notice: str | None = None,
    error: str | None = None,
    error_detail: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the question bank and its section-first generation form."""
    curriculum = CurriculumRepository(session)
    approved = curriculum.get_approved()
    selected_sections = (
        SourceRetrieval(session).sections_in_book(selected_book_id)
        if selected_book_id is not None
        else []
    )
    repo = QuestionRepository(session)
    return render(
        request,
        "questions.html",
        {
            "page_title": "Questions",
            "active_section": "questions",
            "questions": repo.list_recent(),
            "status_counts": repo.count_by_status(),
            "approved_curriculum": curriculum.get_with_tree(approved.id) if approved else None,
            "books": BookRepository(session).list_usable(),
            "selected_book_id": selected_book_id,
            "selected_sections": selected_sections,
            "difficulty_options": list(Difficulty),
            "question_type_options": list(QuestionType),
            "created_count": created_count,
            "created_ids": created_ids,
            "judge_runs": api_evaluation.list_batch_runs(session).runs,
            "judge_batch_status": get_settings().describe_judge_batch(),
            "judge_batch_enabled": get_settings().judge_batch_enabled,
            "judge_notice": judge_notice,
            "error": error,
            "error_detail": error_detail,
        },
        status_code=status_code,
    )


@router.get("/questions", response_class=HTMLResponse, name="questions")
def questions(
    request: Request,
    session: DbSession,
    book_id: int | None = None,
    created: int | None = None,
    ids: str | None = None,
    judge_notice: str | None = None,
) -> HTMLResponse:
    created_ids: list[int] | None = None
    if ids:
        created_ids = [int(part) for part in ids.split(",") if part.strip()]
    return _questions_page(
        request,
        session,
        selected_book_id=book_id,
        created_count=created,
        created_ids=created_ids,
        judge_notice=judge_notice,
    )


@router.post("/questions/judge-runs", name="submit_judge_run_page")
def submit_judge_run_page(request: Request, session: DbSession) -> Response:
    """Submit a bulk judge re-run, then return to the question bank.

    The re-run is asynchronous, so this redirects with a notice rather than
    results: nothing has been judged yet when the professor lands back here.
    """
    try:
        result = api_evaluation.submit_batch_run(session)
    except (ConfigurationError, DomainRuleError, LLMRequestError) as exc:
        return _questions_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
    notice = (
        f"Submitted {result.submitted} question(s) for re-judging as run "
        f"{result.run.run_id}. Results arrive within 24 hours; use "
        f"“Check for results” to collect them."
    )
    if result.backfilled:
        notice += f" Recorded {result.backfilled} earlier evaluation(s) into history first."
    if result.skipped:
        notice += f" Skipped {result.skipped} question(s) whose source context is unavailable."
    return RedirectResponse(
        url=f"/questions?judge_notice={quote(notice)}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/questions/judge-runs/{run_id}/poll", name="poll_judge_run_page")
def poll_judge_run_page(request: Request, session: DbSession, run_id: str) -> Response:
    """Collect whatever a re-run has finished, then return to the question bank."""
    try:
        result = api_evaluation.poll_batch_run(session, run_id)
    except (ConfigurationError, NotFoundError, LLMRequestError) as exc:
        return _questions_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
    if result.ingested or result.failed:
        notice = f"Run {run_id} is {result.status.value}: recorded {result.ingested} evaluation(s)"
        notice += f" and {result.failed} failure(s)." if result.failed else "."
    else:
        notice = f"Run {run_id} is {result.status.value}. No new results yet."
    return RedirectResponse(
        url=f"/questions?judge_notice={quote(notice)}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/questions/generate", name="generate_questions")
def generate_questions(
    request: Request,
    session: DbSession,
    topic_id: Annotated[int, Form()],
    subtopic_id: Annotated[int, Form()],
    difficulty: Annotated[str, Form()],
    question_type: Annotated[str, Form()],
    book_id: Annotated[int, Form()],
    section_ids: Annotated[list[int] | None, Form()] = None,
    all_sections: Annotated[str | None, Form()] = None,
    generator: Annotated[str, Form()] = "base",
) -> Response:
    """Generate one persisted question for every selected source section."""
    try:
        payload = GenerateQuestionsRequest(
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            question_type=QuestionType(question_type),
            difficulty=Difficulty(difficulty),
            book_id=book_id,
            section_ids=section_ids,
            all_sections_of_book=all_sections is not None,
            generator="personalized" if generator == "personalized" else "base",
        )
    except (ValueError, ValidationError) as exc:
        return _questions_page(
            request,
            session,
            selected_book_id=book_id,
            error="Choose a supported difficulty and question type.",
            error_detail=str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    try:
        result = api_questions.generate_questions(session, payload)
    except (
        InvalidQuestionSpecError,
        ConfigurationError,
        LLMRequestError,
        MalformedModelOutputError,
    ) as exc:
        return _questions_page(
            request,
            session,
            selected_book_id=book_id,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )

    if result.created == 1:
        url = f"/questions/{result.question_ids[0]}"
    else:
        id_list = ",".join(str(question_id) for question_id in result.question_ids)
        url = f"/questions?created={result.created}&ids={id_list}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/questions/{question_id}", response_class=HTMLResponse, name="question_detail")
def question_detail(request: Request, session: DbSession, question_id: int) -> HTMLResponse:
    """Show generated content and the citation(s) that ground one question."""
    detail = api_questions.get_question(session, question_id)
    return render(
        request,
        "question_detail.html",
        {
            "page_title": f"Question {detail.question.id}",
            "active_section": "questions",
            "question": detail.question,
            "detail": detail,
            "content": detail.content or {},
            "spec": detail.spec,
            "rejection_reasons": list(REJECTION_REASON_LABELS.items()),
            "sources": detail.sources,
            "taxonomy": detail.taxonomy,
            "validation_checks": detail.validation_checks,
            "validation_passed": detail.validation_passed,
            "pedagogical_eval": detail.pedagogical_eval,
            "pedagogical_error_message": detail.pedagogical_error_message,
            "personalization_evidence": detail.personalization,
            "judge_history": api_evaluation.question_evaluations(session, question_id).evaluations,
        },
    )


@router.post("/questions/{question_id}/review", name="review_question")
def review_question(
    session: DbSession,
    question_id: int,
    decision: Annotated[str, Form()],
    comment: Annotated[str, Form()] = "",
    reasons: Annotated[list[str] | None, Form()] = None,
    prompt: Annotated[str, Form()] = "",
    reference_solution: Annotated[str, Form()] = "",
    tests: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Record a professor verdict and return to the reviewed question."""
    api_feedback.create_review(
        session,
        question_id,
        ReviewRequest(
            decision=ReviewDecision(decision),
            reasons=[RejectionReason(value) for value in (reasons or [])],
            comment=comment or None,
            prompt=prompt,
            reference_solution=reference_solution,
            tests=tests,
        ),
    )
    return RedirectResponse(url=f"/questions/{question_id}", status_code=status.HTTP_303_SEE_OTHER)


def _preferences_page(
    request: Request,
    session: Session,
    *,
    refreshed_count: int | None = None,
    error: str | None = None,
    error_detail: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the Preferences index, optionally with an inline error banner."""
    return render(
        request,
        "preferences.html",
        {
            "page_title": "Preferences",
            "active_section": "preferences",
            "preferences": api_preferences.list_preferences(session).preferences,
            "refreshed_count": refreshed_count,
            "error": error,
            "error_detail": error_detail,
        },
        status_code=status_code,
    )


@router.get("/preferences", response_class=HTMLResponse, name="preferences")
def preferences(
    request: Request,
    session: DbSession,
    refreshed: int | None = None,
) -> HTMLResponse:
    return _preferences_page(request, session, refreshed_count=refreshed)


@router.post("/preferences/refresh", name="refresh_preferences_page")
def refresh_preferences_page(request: Request, session: DbSession) -> Response:
    try:
        result = api_preferences.refresh(session)
    except (ConfigurationError, LLMRequestError) as exc:
        return _preferences_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
    return RedirectResponse(
        url=f"/preferences?refreshed={result.refreshed}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/preferences/{preference_id}/confirm", name="confirm_preference_page")
def confirm_preference_page(session: DbSession, preference_id: int) -> RedirectResponse:
    api_preferences.confirm(session, preference_id)
    return RedirectResponse(url="/preferences", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/preferences/{preference_id}/correct", name="correct_preference_page")
def correct_preference_page(
    request: Request,
    session: DbSession,
    preference_id: int,
    rule_text: Annotated[str, Form()],
) -> Response:
    try:
        payload = CorrectPreferenceRequest(rule_text=rule_text)
        api_preferences.correct(session, preference_id, payload)
    except ValidationError as exc:
        # An empty box fails the request model before the service sees it.
        return _preferences_page(
            request,
            session,
            error="Corrected preference text must not be empty.",
            error_detail=str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    except DomainRuleError as exc:
        return _preferences_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
    return RedirectResponse(url="/preferences", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/preferences/{preference_id}/remove", name="remove_preference_page")
def remove_preference_page(session: DbSession, preference_id: int) -> RedirectResponse:
    api_preferences.remove(session, preference_id)
    return RedirectResponse(url="/preferences", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/feedback", response_class=HTMLResponse, name="feedback")
def feedback(request: Request, session: DbSession) -> HTMLResponse:
    stats = api_feedback.review_stats(session)
    return render(
        request,
        "feedback.html",
        {
            "page_title": "Professor Feedback",
            "active_section": "feedback",
            "stats": stats,
            "reason_distribution": stats.reason_distribution,
            "reviews": api_feedback.list_reviews(session).reviews,
            # Calibration reads the same review history this page already shows,
            # so it belongs here rather than behind a section of its own.
            "calibration": api_calibration.calibration_results(session),
            "calibration_pairs": api_calibration.calibration_pairs(session).pairs,
            "min_informative_sample": MIN_INFORMATIVE_SAMPLE,
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
