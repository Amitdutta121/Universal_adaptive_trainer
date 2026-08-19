"""Question endpoints: generate section-grounded questions and read them back.

Generation always names an approved curriculum version; there is no path that
lets a caller invent taxonomy ids (ADR-001). Which generator ran is explicit and
recorded on the question, so ``base`` and ``personalized-context`` stay
distinguishable rather than being silently swapped (ADR-005).

``generation-plan`` prices a selection without running it. Generation is a
sequence of model calls that cannot be undone once spent, so what a run will
cost is answerable before it starts rather than only afterwards.
"""

from __future__ import annotations

import logging
from collections import Counter
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domain.books import BookSection
from app.domain.enums import Difficulty, JudgeMetricId, QuestionStatus
from app.errors import InvalidQuestionSpecError, NotFoundError
from app.evaluation import (
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
    humanize_judge_error_detail,
)
from app.generation import GenerationService, compile_chunk_requests, count_identical_requests
from app.ingestion import SourceRetrieval
from app.persistence.models import QuestionRow
from app.persistence.repositories import (
    BookRepository,
    CurriculumRepository,
    QuestionRepository,
)
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    BatchPlanResponse,
    BatchPlanTotals,
    BookSummary,
    GenerateBatchRequest,
    GenerateBatchResponse,
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    GenerationPlanChapter,
    GenerationPlanResponse,
    GenerationPlanSection,
    GenerationPlanTotals,
    PersonalizationEvidence,
    PlannedQuestionOut,
    QuestionDetail,
    QuestionListResponse,
    QuestionSummary,
    QuestionTaxonomy,
    ReviewOut,
    ReviewQueueMode,
    ReviewQueueResponse,
    SectionSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("", response_model=QuestionListResponse)
def list_questions(
    session: DbSession,
    limit: int = 50,
    status: QuestionStatus | None = None,
    curriculum_version_id: int | None = None,
) -> QuestionListResponse:
    """The question bank, newest first, with counts by lifecycle status.

    ``status`` and ``curriculum_version_id`` narrow the listing; without them
    nothing is hidden. The API does not filter by default even though the page
    does, because a caller reading the bank over JSON has no way to discover rows
    an unrequested default removed. ``status_counts``, ``curriculum_version_counts``
    and ``total`` always describe the whole bank, so a filtered listing still says
    how much it is showing of what.
    """
    repo = QuestionRepository(session)
    rows = repo.list_recent(
        limit=limit,
        statuses=None if status is None else [status],
        curriculum_version_id=curriculum_version_id,
    )
    return QuestionListResponse(
        questions=[QuestionSummary.from_row(row) for row in rows],
        status_counts=repo.count_by_status(),
        curriculum_version_counts=repo.count_by_curriculum_version(),
        total=repo.count(),
        status=status,
        curriculum_version_id=curriculum_version_id,
    )


@router.post(
    "/generate", response_model=GenerateQuestionsResponse, status_code=status.HTTP_201_CREATED
)
def generate_questions(
    session: DbSession, payload: GenerateQuestionsRequest
) -> GenerateQuestionsResponse:
    """Generate and persist one question per selected source section.

    Every spec is validated before the first model call, so an invalid id later
    in the list cannot leave a partially generated batch behind.
    """
    if payload.all_sections_of_book and payload.book_id is None:
        raise InvalidQuestionSpecError(
            "Generating from a whole book needs a book id.",
            detail="Set book_id, or list section_ids instead.",
        )
    if not payload.all_sections_of_book and not payload.section_ids:
        raise InvalidQuestionSpecError(
            "No source sections were selected.",
            detail="Provide section_ids, or set all_sections_of_book with a book_id.",
        )
    # Resolved before the service is built so that a missing curriculum reports
    # the fixable problem rather than an LLM-configuration error raised first.
    curriculum_version_id = payload.curriculum_version_id or approved_curriculum_id(session)

    try:
        generated = GenerationService(session).generate_for_sections(
            curriculum_version_id=curriculum_version_id,
            question_type=payload.question_type,
            difficulty=payload.difficulty,
            source_section_ids=None if payload.all_sections_of_book else payload.section_ids,
            book_id=payload.book_id if payload.all_sections_of_book else None,
            seed=payload.seed,
        )
    except Exception:
        session.rollback()
        raise

    return GenerateQuestionsResponse(
        created=len(generated),
        question_ids=[row.id for row in generated],
        questions=[QuestionSummary.from_row(row) for row in generated],
    )


@router.post("/batch-plan", response_model=BatchPlanResponse)
def batch_plan(payload: GenerateBatchRequest) -> BatchPlanResponse:
    """Compile a per-chunk spec sheet into the questions it would generate (ADR-044).

    Read-only and free: it makes no model call and touches no row, so a professor
    can price a spec sheet and revise it as often as they like. The compilation
    lives here rather than in either UI because the rule that decides which format
    each question gets must not be restated by a client (ADR-027).
    """
    planned = compile_chunk_requests([chunk.to_request() for chunk in payload.chunks])
    counts = Counter(question.difficulty for question in planned)
    return BatchPlanResponse(
        planned=[PlannedQuestionOut.from_planned(question) for question in planned],
        totals=BatchPlanTotals(
            chunks_specified=len({question.section_id for question in planned}),
            questions_to_create=len(planned),
            generation_calls=len(planned),
            judge_calls=len(planned) * len(JudgeMetricId),
            easy=counts[Difficulty.EASY],
            medium=counts[Difficulty.MEDIUM],
            hard=counts[Difficulty.HARD],
            identical_repeats=count_identical_requests(planned),
        ),
    )


@router.post(
    "/generate-batch", response_model=GenerateBatchResponse, status_code=status.HTTP_201_CREATED
)
def generate_batch(session: DbSession, payload: GenerateBatchRequest) -> GenerateBatchResponse:
    """Generate the questions a per-chunk spec sheet asks for (ADR-044).

    One chunk may produce several questions, at several difficulties, in several
    formats — which is what separates this from ``/generate``, where a run carries
    one difficulty and one format for every section in it.

    The run is synchronous: each question costs one generation call plus one judge
    call per metric, made in sequence. A large sheet is therefore a long request,
    and the console warns before submitting one.
    """
    chunks = [chunk.to_request() for chunk in payload.chunks]
    # Compiled before the service is built so an unusable sheet reports the
    # fixable problem rather than an LLM-configuration error raised first.
    planned = compile_chunk_requests(chunks)
    curriculum_version_id = payload.curriculum_version_id or approved_curriculum_id(session)

    try:
        generated = GenerationService(session).generate_batch(
            curriculum_version_id=curriculum_version_id,
            chunks=chunks,
            seed=payload.seed,
        )
    except Exception:
        session.rollback()
        raise

    return GenerateBatchResponse(
        created=len(generated),
        question_ids=[row.id for row in generated],
        questions=[QuestionSummary.from_row(row) for row in generated],
        planned=[PlannedQuestionOut.from_planned(question) for question in planned],
    )


def approved_curriculum_id(session: Session) -> int:
    """Return the approved curriculum id or raise an actionable generation error."""
    approved = CurriculumRepository(session).get_approved()
    if approved is None:
        raise InvalidQuestionSpecError(
            "No approved curriculum is available.",
            detail="Upload a valid taxonomy before generating questions.",
        )
    return approved.id


# Declared before "/{question_id}": FastAPI matches in registration order, so a
# literal path added after it would be parsed as a question id and 422.
@router.get("/generation-plan", response_model=GenerationPlanResponse)
def generation_plan(
    session: DbSession,
    book_id: int,
    section_ids: Annotated[list[int] | None, Query()] = None,
    all_sections: bool = False,
) -> GenerationPlanResponse:
    """What generating from this selection would produce, before it runs.

    Read-only and free: it makes no model call, so a professor can price a run
    and revise it as often as they like. The arithmetic lives here rather than in
    the template because the page is only one client of it (ADR-027).
    """
    book = BookRepository(session).get(book_id)
    chapters = SourceRetrieval(session).chapters_in_book(book_id)
    already_generated = QuestionRepository(session).count_by_source_section()
    chosen = set(section_ids or [])

    plan_chapters: list[GenerationPlanChapter] = []
    selected_sections: list[BookSection] = []
    for chapter in chapters:
        entries = []
        for section in chapter.sections:
            selected = all_sections or (section.id in chosen)
            if selected:
                selected_sections.append(section)
            entries.append(
                GenerationPlanSection(
                    section=SectionSummary.from_section(section),
                    existing_question_count=already_generated.get(section.id or 0, 0),
                    selected=selected,
                    selectable=not section.is_empty,
                )
            )
        plan_chapters.append(
            GenerationPlanChapter(
                id=chapter.id or 0,
                label=chapter.display_title(),
                location_label=chapter.location_label,
                sections=entries,
            )
        )

    count = len(selected_sections)
    return GenerationPlanResponse(
        book=BookSummary.from_row(book),
        chapters=plan_chapters,
        totals=GenerationPlanTotals(
            sections_available=sum(len(chapter.sections) for chapter in chapters),
            sections_selected=count,
            questions_to_create=count,
            generation_calls=count,
            judge_calls=count * len(JudgeMetricId),
            source_chars=sum(section.char_count for section in selected_sections),
        ),
        blockers=[
            f"{section.display_title()} has no text to generate from."
            for section in selected_sections
            if section.is_empty
        ],
    )


@router.get("/review-queue", response_model=ReviewQueueResponse)
def review_queue(
    session: DbSession, after: int | None = None, mode: ReviewQueueMode = "all"
) -> ReviewQueueResponse:
    """The next question awaiting a professor verdict, plus progress counts.

    The queue holds no state. ``after`` is a plain cursor over question ids,
    which is what lets a professor skip a question -- and lets a submitted
    review advance to the next one -- without a stored position per professor.

    Questions that failed deterministic validation are never offered (ADR-032),
    and ``total`` counts only reviewable ones, so a completed pass reads as
    ``remaining == 0`` rather than stalling on questions the queue excludes.
    """
    repo = QuestionRepository(session)
    scoreable = [row for row in repo.list_unreviewed(require_evaluation=True) if _is_scoreable(row)]

    candidates = repo.list_unreviewed(after_id=after, require_evaluation=mode == "scoreable")
    if mode == "scoreable":
        candidates = [row for row in candidates if _is_scoreable(row)]

    total = repo.count_reviewable()
    reviewed = repo.count_reviewed()
    return ReviewQueueResponse(
        mode=mode,
        total=total,
        reviewed=reviewed,
        remaining=total - reviewed,
        scoreable_remaining=len(scoreable),
        question=get_question(session, candidates[0].id) if candidates else None,
    )


def _is_scoreable(question: QuestionRow) -> bool:
    """Whether this question's stored evaluation can pair with a review.

    Calibration counts a question only when the judge actually reached a verdict,
    so an evaluation that errored, was skipped, or no longer validates is not a
    question worth reviewing *for alignment* -- it can never become a pair.
    """
    if question.pedagogical_eval is None:
        return False
    try:
        evaluation = PedagogicalEvaluation.model_validate(question.pedagogical_eval)
    except ValidationError:
        return False
    return evaluation.status is PedagogicalEvalStatus.COMPLETED


@router.get("/{question_id}", response_model=QuestionDetail)
def get_question(session: DbSession, question_id: int) -> QuestionDetail:
    """One question with its validation report, judge evaluation and provenance."""
    question = QuestionRepository(session).get(question_id)
    report = question.validation_report

    evaluation: PedagogicalEvaluation | None = None
    if question.pedagogical_eval is not None:
        with suppress(ValidationError):
            evaluation = PedagogicalEvaluation.model_validate(question.pedagogical_eval)

    content = question.content or {}
    sources = content.get("sources", [])

    return QuestionDetail(
        question=QuestionSummary.from_row(question),
        reference_solution=question.reference_solution,
        tests=question.tests,
        spec=question.spec,
        content=content,
        sources=sources if isinstance(sources, list) else [],
        taxonomy=resolve_taxonomy(session, question),
        validation_passed=report.passed if report is not None else None,
        validation_checks=report.checks if report is not None else [],
        generation_attempts=list(question.generation_attempts),
        pedagogical_eval=evaluation,
        pedagogical_error_message=(
            humanize_judge_error_detail(evaluation.error_detail)
            if evaluation is not None and evaluation.status is PedagogicalEvalStatus.ERROR
            else None
        ),
        personalization=personalization_evidence(question),
        original_prompt=question.original_prompt,
        original_reference_solution=question.original_reference_solution,
        original_tests=question.original_tests,
        reviews=[ReviewOut.from_row(review) for review in question.reviews],
    )


def resolve_taxonomy(session: Session, question: QuestionRow) -> QuestionTaxonomy:
    """Turn the ids on a question into display names, falling back to the id.

    A question keeps working after its curriculum version is superseded, so a
    name that can no longer be resolved degrades to an em dash rather than 404.
    """
    subtopic_ids = list(question.subtopic_ids)
    taxonomy = QuestionTaxonomy(
        curriculum=str(question.curriculum_version_id or "—"),
        topic=str(question.topic_id or "—"),
        subtopics=[str(subtopic_id) for subtopic_id in subtopic_ids] or ["—"],
    )
    if question.curriculum_version_id is None:
        return taxonomy
    try:
        version = CurriculumRepository(session).get_with_tree(question.curriculum_version_id)
    except NotFoundError:
        return taxonomy

    taxonomy.curriculum = version.label
    topic = next((item for item in version.topics if item.id == question.topic_id), None)
    if topic is None:
        return taxonomy
    taxonomy.topic = topic.name
    names = {item.id: item.name for item in topic.subtopics}
    if subtopic_ids:
        taxonomy.subtopics = [
            names.get(subtopic_id, str(subtopic_id)) for subtopic_id in subtopic_ids
        ]
    return taxonomy


def personalization_evidence(question: QuestionRow) -> PersonalizationEvidence | None:
    """Historical only: what shaped a question generated before ADR-033.

    Personalization is now the per-type instruction, which leaves no per-question
    payload. Nothing generated from here on sets ``personalization_context``, but
    the questions that already carry it keep showing what produced them rather
    than losing that evidence to a refactor.
    """
    payload = question.personalization_context
    if question.generator_name != "personalized-context" or payload is None:
        return None
    preference_ids = payload.get("preference_ids", [])
    review_ids = payload.get("retrieved_review_ids", [])
    profile_version = payload.get("profile_version")
    return PersonalizationEvidence(
        preference_ids=preference_ids if isinstance(preference_ids, list) else [],
        review_ids=review_ids if isinstance(review_ids, list) else [],
        profile_version=str(profile_version) if profile_version is not None else None,
    )
