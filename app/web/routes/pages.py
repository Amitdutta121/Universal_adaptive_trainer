"""Server-rendered professor pages.

Each section page is a placeholder that shows real state from the database
(counts, empty lists) plus an explicit note about what is not implemented yet.
Showing genuine empty state rather than mock data keeps the UI honest.
"""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.curriculum import (
    TaxonomyImportService,
    decode_json_list,
    decode_metadata,
    decode_proposal_warnings,
)
from app.curriculum.taxonomy_schema import SCHEMA_VERSION as TAXONOMY_SCHEMA_VERSION
from app.domain.enums import Difficulty, QuestionType, RejectionReason, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS, decode_reasons
from app.domain.preferences import decode_review_ids
from app.domain.questions import QuestionValidationReport
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
from app.evaluation import (
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
    humanize_judge_error_detail,
)
from app.feedback import submit_review
from app.generation import GenerationService
from app.ingestion import (
    SCHEMA_VERSION,
    SUPPORTED_EXTENSIONS,
    BookImportService,
    SourceRetrieval,
    decode_warnings,
)
from app.llm import describe_availability
from app.persistence.database import get_session
from app.persistence.repositories import (
    BookRepository,
    BookStructureRepository,
    CurriculumRepository,
    PreferenceRepository,
    ProfessorReviewRepository,
    QuestionRepository,
)
from app.personalization import (
    confirm_preference,
    correct_preference,
    refresh_preferences,
    remove_preference,
)
from app.personalization.embeddings import get_embedder
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
    data = file.file.read()
    filename = file.filename or "taxonomy.json"
    try:
        version = TaxonomyImportService(session).import_upload(filename=filename, data=data)
    except (UnsupportedFileError, FileTooLargeError, InvalidTaxonomyDocumentError) as exc:
        session.rollback()
        logger.info("Rejected taxonomy upload %r: %s", filename, exc.message)
        return _curriculum_page(
            request,
            session,
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
    """One curriculum version: the Topic -> Subtopic hierarchy."""
    repo = CurriculumRepository(session)
    version = repo.get_with_tree(version_id)
    book_ids = decode_json_list(version.source_book_ids_json)
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
    """One subtopic: definition and, for legacy rows, textbook evidence."""
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
            "is_taxonomy_upload": (
                subtopic.topic.curriculum_version.generated_by == "taxonomy-upload"
            ),
            "candidate_labels": decode_json_list(subtopic.candidate_labels_json),
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
    selected_generator: Literal["base", "personalized"] = (
        "personalized" if generator == "personalized" else "base"
    )
    service_kwargs: dict[str, object] = {}
    if selected_generator == "personalized":
        try:
            service_kwargs["embedder"] = get_embedder()
        except ConfigurationError as exc:
            session.rollback()
            return _questions_page(
                request,
                session,
                selected_book_id=book_id,
                error=exc.message,
                error_detail=exc.detail,
                status_code=exc.status_code,
            )
    try:
        generated = GenerationService(session, **service_kwargs).generate_for_sections(
            curriculum_version_id=_approved_curriculum_id(session),
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            question_type=QuestionType(question_type),
            difficulty=Difficulty(difficulty),
            source_section_ids=None if all_sections is not None else section_ids,
            book_id=book_id if all_sections is not None else None,
            generator=selected_generator,
        )
    except ValueError as exc:
        session.rollback()
        return _questions_page(
            request,
            session,
            selected_book_id=book_id,
            error="Choose a supported difficulty and question type.",
            error_detail=str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    except (
        InvalidQuestionSpecError,
        ConfigurationError,
        LLMRequestError,
        MalformedModelOutputError,
    ) as exc:
        session.rollback()
        return _questions_page(
            request,
            session,
            selected_book_id=book_id,
            error=exc.message,
            error_detail=exc.detail,
            status_code=exc.status_code,
        )

    if len(generated) == 1:
        url = f"/questions/{generated[0].id}"
    else:
        id_list = ",".join(str(row.id) for row in generated)
        url = f"/questions?created={len(generated)}&ids={id_list}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _approved_curriculum_id(session: Session) -> int:
    """Return the approved curriculum id or raise an actionable generation error."""
    approved = CurriculumRepository(session).get_approved()
    if approved is None:
        raise InvalidQuestionSpecError(
            "No approved curriculum is available.",
            detail="Upload a valid taxonomy before generating questions.",
        )
    return approved.id


@router.get("/questions/{question_id}", response_class=HTMLResponse, name="question_detail")
def question_detail(request: Request, session: DbSession, question_id: int) -> HTMLResponse:
    """Show generated content and the citation(s) that ground one question."""
    question = QuestionRepository(session).get(question_id)
    validation_report = None
    if question.validation_report_json:
        with suppress(ValidationError):
            validation_report = QuestionValidationReport.model_validate_json(
                question.validation_report_json
            )
    pedagogical_eval = None
    if question.pedagogical_eval_json:
        with suppress(ValidationError):
            pedagogical_eval = PedagogicalEvaluation.model_validate_json(
                question.pedagogical_eval_json
            )
    try:
        content = json.loads(question.content_json or "{}")
    except json.JSONDecodeError:
        content = {}
    if not isinstance(content, dict):
        content = {}
    spec = None
    if question.spec_json:
        with suppress(json.JSONDecodeError, TypeError):
            parsed_spec = json.loads(question.spec_json)
            spec = parsed_spec if isinstance(parsed_spec, dict) else None
    sources = content.get("sources", [])
    taxonomy = {
        "curriculum": str(question.curriculum_version_id or "—"),
        "topic": str(question.topic_id or "—"),
        "subtopic": str(question.subtopic_id or "—"),
    }
    if question.curriculum_version_id is not None:
        try:
            version = CurriculumRepository(session).get_with_tree(question.curriculum_version_id)
        except NotFoundError:
            pass
        else:
            taxonomy["curriculum"] = version.label
            topic = next((item for item in version.topics if item.id == question.topic_id), None)
            if topic is not None:
                taxonomy["topic"] = topic.name
                subtopic = next(
                    (item for item in topic.subtopics if item.id == question.subtopic_id), None
                )
                if subtopic is not None:
                    taxonomy["subtopic"] = subtopic.name
    personalization_evidence = None
    if question.generator_name == "personalized-context" and question.personalization_context_json:
        with suppress(json.JSONDecodeError, TypeError):
            payload = json.loads(question.personalization_context_json)
            if isinstance(payload, dict):
                preference_ids = payload.get("preference_ids", [])
                review_ids = payload.get("retrieved_review_ids", [])
                personalization_evidence = {
                    "preference_ids": preference_ids if isinstance(preference_ids, list) else [],
                    "review_ids": review_ids if isinstance(review_ids, list) else [],
                }
    return render(
        request,
        "question_detail.html",
        {
            "page_title": f"Question {question.id}",
            "active_section": "questions",
            "question": question,
            "content": content,
            "spec": spec,
            "rejection_reasons": list(REJECTION_REASON_LABELS.items()),
            "sources": sources if isinstance(sources, list) else [],
            "taxonomy": taxonomy,
            "validation_checks": validation_report.checks if validation_report else [],
            "validation_passed": validation_report.passed if validation_report else None,
            "pedagogical_eval": pedagogical_eval,
            "pedagogical_error_message": (
                humanize_judge_error_detail(pedagogical_eval.error_detail)
                if pedagogical_eval is not None
                and pedagogical_eval.status is PedagogicalEvalStatus.ERROR
                else None
            ),
            "personalization_evidence": personalization_evidence,
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
    decision_enum = ReviewDecision(decision)
    parsed_reasons = [RejectionReason(value) for value in (reasons or [])]
    if decision_enum is ReviewDecision.EDIT:
        submit_review(
            session,
            question_id=question_id,
            decision=decision_enum,
            reasons=parsed_reasons,
            comment=comment or None,
            prompt=prompt,
            reference_solution=reference_solution,
            tests=tests,
            professor_id=None,
        )
    else:
        submit_review(
            session,
            question_id=question_id,
            decision=decision_enum,
            reasons=parsed_reasons,
            comment=comment or None,
            professor_id=None,
        )
    session.commit()
    return RedirectResponse(url=f"/questions/{question_id}", status_code=status.HTTP_303_SEE_OTHER)


def _preference_rows(session: Session) -> list[dict[str, object]]:
    rows = []
    for pref in PreferenceRepository(session).list_all():
        category = pref.category.value if hasattr(pref.category, "value") else pref.category
        state = (
            pref.confirmation_state.value
            if hasattr(pref.confirmation_state, "value")
            else pref.confirmation_state
        )
        rows.append(
            {
                "id": pref.id,
                "rule_text": pref.rule_text,
                "category_label": str(category).replace("_", " "),
                "evidence_count": pref.evidence_count,
                "confidence": pref.confidence,
                "state": state,
                "active": pref.active,
                "review_ids": decode_review_ids(pref.supporting_review_ids_json),
            }
        )
    return rows


@router.get("/preferences", response_class=HTMLResponse, name="preferences")
def preferences(
    request: Request,
    session: DbSession,
    refreshed: int | None = None,
) -> HTMLResponse:
    return render(
        request,
        "preferences.html",
        {
            "page_title": "Preferences",
            "active_section": "preferences",
            "preferences": _preference_rows(session),
            "refreshed_count": refreshed,
        },
    )


@router.post("/preferences/refresh", name="refresh_preferences_page")
def refresh_preferences_page(request: Request, session: DbSession) -> Response:
    try:
        count = refresh_preferences(session)
    except (ConfigurationError, LLMRequestError) as exc:
        session.rollback()
        return render(
            request,
            "preferences.html",
            {
                "page_title": "Preferences",
                "active_section": "preferences",
                "preferences": _preference_rows(session),
                "error": exc.message,
                "error_detail": exc.detail,
            },
            status_code=exc.status_code,
        )
    return RedirectResponse(
        url=f"/preferences?refreshed={count}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/preferences/{preference_id}/confirm", name="confirm_preference_page")
def confirm_preference_page(session: DbSession, preference_id: int) -> RedirectResponse:
    confirm_preference(session, preference_id)
    return RedirectResponse(url="/preferences", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/preferences/{preference_id}/correct", name="correct_preference_page")
def correct_preference_page(
    request: Request,
    session: DbSession,
    preference_id: int,
    rule_text: Annotated[str, Form()],
) -> Response:
    try:
        correct_preference(session, preference_id, rule_text)
    except DomainRuleError as exc:
        session.rollback()
        return render(
            request,
            "preferences.html",
            {
                "page_title": "Preferences",
                "active_section": "preferences",
                "preferences": _preference_rows(session),
                "error": exc.message,
                "error_detail": exc.detail,
            },
            status_code=exc.status_code,
        )
    return RedirectResponse(url="/preferences", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/preferences/{preference_id}/remove", name="remove_preference_page")
def remove_preference_page(session: DbSession, preference_id: int) -> RedirectResponse:
    remove_preference(session, preference_id)
    return RedirectResponse(url="/preferences", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/feedback", response_class=HTMLResponse, name="feedback")
def feedback(request: Request, session: DbSession) -> HTMLResponse:
    repo = ProfessorReviewRepository(session)
    by_decision = repo.count_by_decision()
    reason_counts = repo.reason_counts()
    review_rows = [
        {
            "id": review.id,
            "question_id": review.question_id,
            "decision": review.decision,
            "reasons": [
                REJECTION_REASON_LABELS[reason] for reason in decode_reasons(review.reasons_json)
            ],
            "comment": review.comment,
            "generator": (f"{review.reviewed_generator_name}@{review.reviewed_generator_version}"),
            "created_at": review.created_at,
        }
        for review in repo.list_recent()
    ]
    return render(
        request,
        "feedback.html",
        {
            "page_title": "Professor Feedback",
            "active_section": "feedback",
            "stats": {
                "reviewed": repo.count(),
                "approved": by_decision.get(ReviewDecision.APPROVE.value, 0),
                "rejected": by_decision.get(ReviewDecision.REJECT.value, 0),
                "edited": by_decision.get(ReviewDecision.EDIT.value, 0),
            },
            "reason_distribution": [
                {
                    "code": code,
                    "label": REJECTION_REASON_LABELS[RejectionReason(code)],
                    "count": count,
                }
                for code, count in sorted(
                    reason_counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            "reviews": review_rows,
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
