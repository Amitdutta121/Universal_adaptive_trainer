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

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.calibration import HELD_OUT_DIVISOR, MIN_INFORMATIVE_SAMPLE
from app.config import get_settings
from app.curriculum import extraction_metadata, proposal_warnings
from app.curriculum.taxonomy_schema import SCHEMA_VERSION as TAXONOMY_SCHEMA_VERSION
from app.domain.enums import (
    Difficulty,
    JudgeMetricId,
    QuadrantCell,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
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
    NoQuestionAvailableError,
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
from app.web.routes.api import coverage as api_coverage
from app.web.routes.api import curriculum as api_curriculum
from app.web.routes.api import evaluation as api_evaluation
from app.web.routes.api import feedback as api_feedback
from app.web.routes.api import instructions as api_instructions
from app.web.routes.api import judge_prompts as api_judge_prompts
from app.web.routes.api import questions as api_questions
from app.web.routes.api import students as api_students
from app.web.routes.api import system as api_system
from app.web.routes.api.schemas import (
    AnswerRequest,
    CreateQuestionSetRequest,
    CreateStudentRequest,
    GenerateQuestionsRequest,
    JudgePromptRequest,
    ReviewOutcomeOut,
    ReviewQueueMode,
    ReviewRequest,
    StartTrainingSessionRequest,
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
        "instructions": totals.learned_instructions,
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


#: Above this many sections, generation asks for confirmation first. A run is a
#: sequence of model calls that cannot be recalled once spent, so a large one is
#: worth one deliberate click; a small one is not worth the friction.
GENERATION_CONFIRM_THRESHOLD = 5


def _questions_page(
    request: Request,
    session: Session,
    *,
    selected_book_id: int | None = None,
    selected_section_ids: list[int] | None = None,
    all_sections: bool = False,
    chapter_id: int | None = None,
    difficulty: str | None = None,
    question_type: str | None = None,
    created_count: int | None = None,
    created_ids: list[int] | None = None,
    judge_notice: str | None = None,
    show_failed: bool = False,
    error: str | None = None,
    error_detail: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the question bank, the chunk plan and the generation form.

    Every choice the professor has made is passed back into the template, so an
    error banner re-renders the form they were looking at rather than resetting
    it.
    """
    curriculum = CurriculumRepository(session)
    approved = curriculum.get_approved()
    repo = QuestionRepository(session)
    # Questions that failed deterministic validation are hidden by default: they
    # are kept as evidence of how the generator fails (ADR-032), not as candidates,
    # and unfiltered they would crowd out the bank. The status counts below always
    # describe the whole bank, so the omission is stated rather than silent.
    bank_statuses = (
        None
        if show_failed
        else [status for status in QuestionStatus if status is not QuestionStatus.VALIDATION_FAILED]
    )
    status_counts = repo.count_by_status()

    plan = None
    section_texts: dict[int, str] = {}
    if selected_book_id is not None:
        try:
            plan = api_questions.generation_plan(
                session,
                book_id=selected_book_id,
                section_ids=selected_section_ids,
                all_sections=all_sections,
            )
            # The plan deliberately carries no text: the page reads it from the
            # domain objects instead, the way book_detail.html does.
            section_texts = {
                section.id: section.text
                for section in SourceRetrieval(session).sections_in_book(selected_book_id)
                if section.id is not None
            }
        except NotFoundError:
            plan = None

    visible_chapters = plan.chapters if plan else []
    if plan and chapter_id is not None:
        visible_chapters = [chapter for chapter in plan.chapters if chapter.id == chapter_id]

    return render(
        request,
        "questions.html",
        {
            "page_title": "Questions",
            "active_section": "questions",
            "questions": repo.list_recent(statuses=bank_statuses),
            "status_counts": status_counts,
            "show_failed": show_failed,
            "failed_count": status_counts.get(QuestionStatus.VALIDATION_FAILED.value, 0),
            "approved_curriculum": curriculum.get_with_tree(approved.id) if approved else None,
            "books": BookRepository(session).list_usable(),
            "selected_book_id": selected_book_id,
            "plan": plan,
            "visible_chapters": visible_chapters,
            "section_texts": section_texts,
            "chapter_id": chapter_id,
            "all_sections": all_sections,
            "difficulty_options": list(Difficulty),
            "question_type_options": list(QuestionType),
            "selected_difficulty": difficulty,
            "selected_question_type": question_type,
            "confirm_threshold": GENERATION_CONFIRM_THRESHOLD,
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
    section_ids: Annotated[list[int] | None, Query()] = None,
    chapter_id: int | None = None,
    difficulty: str | None = None,
    question_type: str | None = None,
    created: int | None = None,
    ids: str | None = None,
    judge_notice: str | None = None,
    show_failed: bool = False,
) -> HTMLResponse:
    created_ids: list[int] | None = None
    if ids:
        created_ids = [int(part) for part in ids.split(",") if part.strip()]
    return _questions_page(
        request,
        session,
        selected_book_id=book_id,
        selected_section_ids=section_ids,
        chapter_id=chapter_id,
        difficulty=difficulty,
        question_type=question_type,
        created_count=created,
        created_ids=created_ids,
        judge_notice=judge_notice,
        show_failed=show_failed,
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
    difficulty: Annotated[str, Form()],
    question_type: Annotated[str, Form()],
    book_id: Annotated[int, Form()],
    section_ids: Annotated[list[int] | None, Form()] = None,
    all_sections: Annotated[str | None, Form()] = None,
    confirmed: Annotated[str | None, Form()] = None,
) -> Response:
    """Generate one persisted question for every selected source section.

    A large run renders a confirmation page instead of generating, and only
    proceeds once it comes back with ``confirmed`` set. The check lives in this
    handler rather than in a separate confirm route so there is one entry point
    to generation, and no second URL that quietly skips the step.
    """
    try:
        payload = GenerateQuestionsRequest(
            question_type=QuestionType(question_type),
            difficulty=Difficulty(difficulty),
            book_id=book_id,
            section_ids=section_ids,
            all_sections_of_book=all_sections is not None,
        )
    except (ValueError, ValidationError) as exc:
        return _questions_page(
            request,
            session,
            selected_book_id=book_id,
            selected_section_ids=section_ids,
            all_sections=all_sections is not None,
            error="Choose a supported difficulty and question type.",
            error_detail=str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    if confirmed is None and _needs_confirmation(payload):
        return _confirmation_page(request, session, payload, book_id)

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
            selected_section_ids=section_ids,
            all_sections=all_sections is not None,
            difficulty=difficulty,
            question_type=question_type,
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


def _needs_confirmation(payload: GenerateQuestionsRequest) -> bool:
    """Whether this run is large enough to be worth confirming first.

    A whole-book run always is: its size is whatever the book happens to hold,
    which is exactly the number the professor cannot see when they tick the box.
    """
    if payload.all_sections_of_book:
        return True
    return len(payload.section_ids or []) > GENERATION_CONFIRM_THRESHOLD


def _confirmation_page(
    request: Request, session: Session, payload: GenerateQuestionsRequest, book_id: int
) -> HTMLResponse:
    """Show what a run will do, and carry the selection forward unchanged."""
    plan = api_questions.generation_plan(
        session,
        book_id=book_id,
        section_ids=payload.section_ids,
        all_sections=payload.all_sections_of_book,
    )
    return render(
        request,
        "questions_confirm.html",
        {
            "page_title": "Confirm generation",
            "active_section": "questions",
            "plan": plan,
            "payload": payload,
            "section_ids": [
                item.section.id
                for chapter in plan.chapters
                for item in chapter.sections
                if item.selected
            ],
        },
    )


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
            "generation_attempts": detail.generation_attempts,
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


def _review_queue_page(
    request: Request,
    session: Session,
    *,
    after: int | None,
    mode: str,
    error: str | None = None,
    error_detail: str | None = None,
    outcome: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the review queue at its current cursor.

    An unknown mode falls back to ``all`` rather than 422: this route is reached
    by hand-editable links, and a mistyped one should still show a question.
    """
    queue_mode: ReviewQueueMode = "scoreable" if mode == "scoreable" else "all"
    queue = api_questions.review_queue(session, after=after, mode=queue_mode)
    detail = queue.question
    return render(
        request,
        "review.html",
        {
            "page_title": "Review queue",
            "active_section": "questions",
            "queue": queue,
            "mode": queue_mode,
            "after": after,
            "detail": detail,
            "question": detail.question if detail else None,
            "content": (detail.content or {}) if detail else {},
            "rejection_reasons": list(REJECTION_REASON_LABELS.items()),
            "error": error,
            "error_detail": error_detail,
            "outcome": outcome,
        },
        status_code=status_code,
    )


@router.get("/review", response_class=HTMLResponse, name="review_queue")
def review_queue_page(
    request: Request,
    session: DbSession,
    after: int | None = None,
    mode: str = "all",
    outcome: str | None = None,
) -> HTMLResponse:
    """Review one question at a time, in one screen, without leaving the queue.

    ``outcome`` carries what the previous submit did (ADR-037) across the
    redirect, so the professor reads it on the next question instead of having
    to open the calibration page to find out.
    """
    return _review_queue_page(request, session, after=after, mode=mode, outcome=outcome)


@router.post("/review/{question_id}", name="submit_queue_review")
def submit_queue_review(
    request: Request,
    session: DbSession,
    question_id: int,
    decision: Annotated[str, Form()],
    comment: Annotated[str, Form()] = "",
    reasons: Annotated[list[str] | None, Form()] = None,
    prompt: Annotated[str, Form()] = "",
    reference_solution: Annotated[str, Form()] = "",
    tests: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "all",
) -> Response:
    """Record a verdict and advance to the next question in one step.

    Advancing on submit is the point of this route: the question detail page
    returns to the question just reviewed, which costs two navigations per
    verdict and makes a hundred-question pass far slower than it needs to be.
    """
    try:
        result = api_feedback.create_review(
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
    except (DomainRuleError, NotFoundError) as exc:
        # Re-offer the same question: the cursor must not advance past a verdict
        # that was never recorded.
        return _review_queue_page(
            request,
            session,
            after=question_id - 1,
            mode=mode,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
    notice = quote(_outcome_notice(question_id, result.outcome))
    return RedirectResponse(
        url=f"/review?after={question_id}&mode={mode}&outcome={notice}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _outcome_notice(question_id: int, outcome: ReviewOutcomeOut | None) -> str:
    """One line saying where the review landed and what was done about it.

    Says "not measured" rather than nothing when the question carried no judge
    verdict. Silence would read as agreement, and the professor would have no
    way to tell a question the judge got right from one it never answered.
    """
    if outcome is None:
        return f"#{question_id}: recorded. No judge verdict to compare, so nothing was measured."

    line = f"#{question_id}: {outcome.cell.value.replace('_', ' ')}."
    if outcome.attributed_labels:
        line += f" Reviewer(s) at fault: {', '.join(outcome.attributed_labels)}."
    elif outcome.cell in (QuadrantCell.MISSED, QuadrantCell.FALSE_ALARM):
        line += " No single reviewer accounts for it."
    learned = []
    if outcome.instruction_refreshed:
        learned.append(f"the {outcome.refresh_rule_count}-rule type instruction")
    if outcome.judges_refreshed:
        learned.append(
            "the "
            + ", ".join(m.value.replace("_", " ") for m in outcome.judges_refreshed)
            + " reviewer"
        )
    if learned:
        line += f" Relearned: {' and '.join(learned)}."
    elif outcome.cell is QuadrantCell.CONFIRMED_BAD and not outcome.refresh_error:
        line += " No review of this type to learn from yet."
    if outcome.refresh_error:
        line += f" Relearning failed: {outcome.refresh_error}"
    return line


def _instructions_page(
    request: Request,
    session: Session,
    *,
    refreshed: str | None = None,
    error: str | None = None,
    error_detail: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the learned per-type instructions (ADR-033)."""
    return render(
        request,
        "instructions.html",
        {
            "page_title": "Instructions",
            "active_section": "instructions",
            "instructions": api_instructions.list_instructions(session).instructions,
            "refreshed": refreshed,
            "error": error,
            "error_detail": error_detail,
        },
        status_code=status_code,
    )


@router.get("/instructions", response_class=HTMLResponse, name="instructions")
def instructions(
    request: Request,
    session: DbSession,
    refreshed: str | None = None,
) -> HTMLResponse:
    return _instructions_page(request, session, refreshed=refreshed)


@router.post("/instructions/{question_type}/refresh", name="refresh_instruction_page")
def refresh_instruction_page(
    request: Request, session: DbSession, question_type: QuestionType
) -> Response:
    try:
        result = api_instructions.refresh(session, question_type)
    except (ConfigurationError, LLMRequestError, MalformedModelOutputError) as exc:
        return _instructions_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
    notice = (
        f"{result.question_type.value}: {result.rule_count} rule(s) from "
        f"{result.review_count} review(s)."
        if result.learned
        else f"{result.question_type.value}: no reviews yet, instruction unchanged."
    )
    return RedirectResponse(
        url=f"/instructions?refreshed={quote(notice)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _judges_page(
    request: Request,
    session: Session,
    *,
    saved: str | None = None,
    error: str | None = None,
    error_detail: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the four judge prompts, editable (ADR-038)."""
    listing = api_judge_prompts.list_judge_prompts(session)
    return render(
        request,
        "judges.html",
        {
            "page_title": "Judges",
            "active_section": "judges",
            "prompts": listing.prompts,
            "rubric_version": listing.rubric_version,
            "shipped_rubric_version": listing.shipped_rubric_version,
            "saved": saved,
            "error": error,
            "error_detail": error_detail,
        },
        status_code=status_code,
    )


@router.get("/judges", response_class=HTMLResponse, name="judges")
def judges(request: Request, session: DbSession, saved: str | None = None) -> HTMLResponse:
    return _judges_page(request, session, saved=saved)


@router.post("/judges/{metric}", name="save_judge_prompt_page")
def save_judge_prompt_page(
    request: Request,
    session: DbSession,
    metric: JudgeMetricId,
    system_prompt: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    revert: Annotated[str | None, Form()] = None,
) -> Response:
    """Save or revert one judge prompt, then report the version it now answers under."""
    try:
        if revert is not None:
            result = api_judge_prompts.revert_judge_prompt(session, metric)
            notice = f"{metric.value}: reverted to the shipped prompt."
        else:
            result = api_judge_prompts.save_judge_prompt(
                session, metric, JudgePromptRequest(system_prompt=system_prompt, note=note or None)
            )
            notice = f"{metric.value}: saved (edit {result.prompt.revision})."
    except (DomainRuleError, NotFoundError, ValidationError) as exc:
        message = getattr(exc, "message", "The judge prompt must not be empty.")
        return _judges_page(
            request,
            session,
            error=message,
            error_detail=getattr(exc, "detail", None),
            status_code=getattr(exc, "status_code", 400),
        )
    notice += f" Judges now answer as {result.rubric_version}."
    return RedirectResponse(
        url=f"/judges?saved={quote(notice)}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/judges/{metric}/refresh", name="refresh_judge_page")
def refresh_judge_page(request: Request, session: DbSession, metric: JudgeMetricId) -> Response:
    """Relearn one judge's prompt from the cases it got wrong (ADR-039)."""
    try:
        result = api_judge_prompts.refresh(session, metric)
    except (ConfigurationError, LLMRequestError, MalformedModelOutputError) as exc:
        return _judges_page(
            request,
            session,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )
    notice = (
        f"{metric.value}: {result.rule_count} rule(s) from {result.evidence_count} "
        f"disagreement(s). Judges now answer as {result.rubric_version}."
        if result.learned
        else f"{metric.value}: nothing has contradicted it yet, so the prompt is unchanged."
    )
    return RedirectResponse(
        url=f"/judges?saved={quote(notice)}", status_code=status.HTTP_303_SEE_OTHER
    )


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
            # The same pairs split four ways and per question type, because the
            # type is the unit a professor would ever authorise (ADR-034).
            "quadrant": api_calibration.calibration_quadrant(session),
            "min_informative_sample": MIN_INFORMATIVE_SAMPLE,
            "held_out_divisor": HELD_OUT_DIVISOR,
        },
    )


def _coverage_page(
    request: Request,
    session: Session,
    *,
    set_version_id: int | None = None,
    created: str | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the coverage grid for the live bank or one frozen set (ADR-036)."""
    return render(
        request,
        "coverage.html",
        {
            "page_title": "Coverage",
            "active_section": "coverage",
            "coverage": api_coverage.coverage(session, set_version_id=set_version_id),
            "question_sets": api_coverage.list_question_sets(session).sets,
            "selected_set_id": set_version_id,
            "created": created,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/coverage", response_class=HTMLResponse, name="coverage")
def coverage(
    request: Request,
    session: DbSession,
    set_version_id: int | None = None,
    created: str | None = None,
) -> HTMLResponse:
    return _coverage_page(request, session, set_version_id=set_version_id, created=created)


@router.post("/coverage/sets", name="create_question_set_page")
def create_question_set_page(
    request: Request,
    session: DbSession,
    label: Annotated[str, Form()],
    notes: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        result = api_coverage.create_set(
            session, CreateQuestionSetRequest(label=label, notes=notes or None)
        )
    except DomainRuleError as exc:
        return _coverage_page(request, session, error=exc.message, status_code=exc.status_code)
    notice = f"{result.label}: {result.question_count} question(s) frozen as set #{result.id}."
    return RedirectResponse(
        url=f"/coverage?created={quote(notice)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _students_page(
    request: Request,
    session: Session,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    listing = api_students.list_students(session)
    return render(
        request,
        "students.html",
        {
            "page_title": "Students",
            "active_section": "students",
            "students": listing.students,
            "question_sets": api_coverage.list_question_sets(session).sets,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/students", response_class=HTMLResponse, name="students")
def students(request: Request, session: DbSession) -> HTMLResponse:
    """Enrolled learners, and where to start a training run."""
    return _students_page(request, session)


@router.post("/students", name="create_student_page")
def create_student_page(
    request: Request,
    session: DbSession,
    display_name: Annotated[str, Form()],
) -> Response:
    try:
        api_students.create_student(session, CreateStudentRequest(display_name=display_name))
    except DomainRuleError as exc:
        return _students_page(request, session, error=exc.message, status_code=exc.status_code)
    except ValidationError:
        return _students_page(
            request,
            session,
            error="That name is not usable. A name is required and may be at most 200 characters.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return RedirectResponse(url="/students", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/students/{student_id}", response_class=HTMLResponse, name="student_detail")
def student_detail(request: Request, session: DbSession, student_id: int) -> HTMLResponse:
    """One learner's measured mastery, weakness and history."""
    progress = api_students.student_progress(session, student_id)
    return render(
        request,
        "student_detail.html",
        {
            "page_title": progress.student.display_name,
            "active_section": "students",
            "progress": progress,
            "question_sets": api_coverage.list_question_sets(session).sets,
        },
    )


@router.post("/students/{student_id}/sessions", name="start_training_session_page")
def start_training_session_page(
    request: Request,
    session: DbSession,
    student_id: int,
    set_version_id: Annotated[int, Form()],
) -> Response:
    try:
        run = api_students.start_training_session(
            session,
            StartTrainingSessionRequest(student_id=student_id, set_version_id=set_version_id),
        )
    except (DomainRuleError, NotFoundError) as exc:
        return _students_page(request, session, error=exc.message, status_code=exc.status_code)
    return RedirectResponse(url=f"/training/{run.id}", status_code=status.HTTP_303_SEE_OTHER)


def _training_page(
    request: Request,
    session: Session,
    training_session_id: int,
    *,
    result: object | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a training session: either its current question, or a just-scored answer.

    A question is drawn only when no result is being shown. Otherwise reporting a
    score would silently serve the next question as well, and the student would
    never see what they got right.
    """
    run = api_students.get_training_session(session, training_session_id)
    served = None
    unavailable = None
    if result is None and run.ended_at is None:
        try:
            served = api_students.next_question(session, training_session_id)
        except NoQuestionAvailableError as exc:
            unavailable = f"{exc.message} {exc.detail or ''}".strip()
        except DomainRuleError as exc:
            error = error or exc.message
    return render(
        request,
        "training.html",
        {
            "page_title": f"Training · {run.student_name}",
            "active_section": "students",
            "run": run,
            "served": served,
            "result": result,
            "unavailable": unavailable,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/training/{training_session_id}", response_class=HTMLResponse, name="training")
def training(request: Request, session: DbSession, training_session_id: int) -> HTMLResponse:
    """The session's current question."""
    return _training_page(request, session, training_session_id)


@router.post("/training/{training_session_id}/answer", name="submit_training_answer_page")
def submit_training_answer_page(
    request: Request,
    session: DbSession,
    training_session_id: int,
    attempt_id: Annotated[int, Form()],
    answer: Annotated[str, Form()] = "",
) -> Response:
    """Score an answer and show the result, rather than redirecting.

    The failing-test evidence and the author's explanation are produced by
    scoring and are not stored on the attempt, so a redirect would lose exactly
    the part the student learns from.
    """
    try:
        result = api_students.answer_attempt(session, attempt_id, AnswerRequest(answer=answer))
    except (DomainRuleError, NotFoundError) as exc:
        return _training_page(
            request, session, training_session_id, error=exc.message, status_code=exc.status_code
        )
    return _training_page(request, session, training_session_id, result=result)


@router.post("/training/{training_session_id}/end", name="end_training_session_page")
def end_training_session_page(
    request: Request, session: DbSession, training_session_id: int
) -> Response:
    run = api_students.end_training_session(session, training_session_id)
    return RedirectResponse(
        url=f"/students/{run.student_id}", status_code=status.HTTP_303_SEE_OTHER
    )
