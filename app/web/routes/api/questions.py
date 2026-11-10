"""Question endpoints: generate chunk-grounded questions and read them back.

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

from fastapi import APIRouter, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adaptive.service import variants_of
from app.domain.enums import Difficulty, JobKind, JudgeMetricId, QuestionStatus
from app.errors import (
    CodeExecutionUnavailableError,
    DomainRuleError,
    InvalidQuestionSpecError,
    NotFoundError,
)
from app.evaluation import (
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
    humanize_judge_error_detail,
    new_run_id,
)
from app.evaluation.severity import borderline_notes
from app.evaluation.trust import judge_trust
from app.generation import GenerationService, compile_chunk_requests, count_identical_requests
from app.generation.computed import regenerate_copy
from app.generation.service import regeneration_spec
from app.generation.spec import require_approved_version
from app.jobs.queue import JobQueue
from app.jobs.runner import Progress, create_job, execute
from app.persistence.models import BackgroundJobRow, QuestionRow
from app.persistence.repositories import (
    CurriculumRepository,
    QuestionEvaluationRepository,
    QuestionRepository,
)
from app.web.routes.api.deps import (
    CourseScope,
    DbSession,
    chunks_in_course,
    ensure_question_types_allowed,
    question_in_course,
    version_in_course,
)
from app.web.routes.api.schemas import (
    BatchPlanResponse,
    BatchPlanTotals,
    ChunkGenerationSpec,
    FigureCopyOut,
    GenerateBatchRequest,
    GenerateBatchResponse,
    JobStartedResponse,
    PersonalizationEvidence,
    PlannedQuestionOut,
    QuestionDetail,
    QuestionListResponse,
    QuestionSummary,
    QuestionTaxonomy,
    RegenerateQuestionResponse,
    ReviewOut,
    ReviewQueueMode,
    ReviewQueueResponse,
)
from graders import ExecutorError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("", response_model=QuestionListResponse)
def list_questions(
    session: DbSession,
    course: CourseScope,
    limit: int = 50,
    status: Annotated[list[QuestionStatus] | None, Query()] = None,
    curriculum_version_id: int | None = None,
    topic_id: Annotated[list[int] | None, Query()] = None,
    chunk_id: str | None = None,
    run_id: str | None = None,
) -> QuestionListResponse:
    """The question bank, newest first, with counts by lifecycle status.

    ``status`` and ``topic_id`` (each repeatable: ``?status=a&status=b`` keeps
    either), ``curriculum_version_id``, ``chunk_id`` and ``run_id`` narrow the
    listing; without them nothing is hidden. The API does not filter by
    default even though the page does, because a caller reading the bank over
    JSON has no way to discover rows an unrequested default removed.
    ``status_counts``, ``curriculum_version_counts`` and ``total`` always
    describe the whole bank, so a filtered listing still says how much it is
    showing of what.
    """
    # Another course's taxonomy or chunk is a 404, not an empty page (ADR-060).
    if curriculum_version_id is not None and course is not None:
        version_in_course(session, curriculum_version_id, course)
    if chunk_id is not None:
        chunks_in_course(session, [chunk_id], course)
    repo = QuestionRepository(session)
    rows = repo.list_recent(
        limit=limit,
        statuses=status or None,
        curriculum_version_id=curriculum_version_id,
        topic_ids=topic_id or None,
        chunk_id=chunk_id,
        run_id=run_id,
        course_id=course,
    )
    return QuestionListResponse(
        questions=[QuestionSummary.from_row(row) for row in rows],
        status_counts=repo.count_by_status(course_id=course),
        curriculum_version_counts=repo.count_by_curriculum_version(course_id=course),
        total=repo.count(course_id=course),
        status=status or None,
        curriculum_version_id=curriculum_version_id,
        topic_id=topic_id or None,
        run_id=run_id,
    )


def plan_chunk_sheet(sheet: list[ChunkGenerationSpec]) -> BatchPlanResponse:
    """The compiled plan and its call counts. Makes no model call and touches no row."""
    planned = compile_chunk_requests([chunk.to_request() for chunk in sheet])
    counts = Counter(question.difficulty for question in planned)
    return BatchPlanResponse(
        planned=[PlannedQuestionOut.from_planned(question) for question in planned],
        totals=BatchPlanTotals(
            chunks_specified=len({question.chunk_id for question in planned}),
            questions_to_create=len(planned),
            generation_calls=len(planned),
            judge_calls=len(planned) * len(JudgeMetricId),
            easy=counts[Difficulty.EASY],
            medium=counts[Difficulty.MEDIUM],
            hard=counts[Difficulty.HARD],
            identical_repeats=count_identical_requests(planned),
        ),
    )


def queue_chunk_sheet(
    session: Session, course: int | None, payload: GenerateBatchRequest, queue: JobQueue
) -> JobStartedResponse:
    """Check a per-chunk spec sheet against the course, then queue it as a bulk job."""
    chunks = [chunk.to_request() for chunk in payload.chunks]
    ensure_question_types_allowed(
        session, course, [qt.value for chunk in chunks for qt in chunk.question_types]
    )
    if payload.curriculum_version_id is not None:
        version_in_course(session, payload.curriculum_version_id, course)
    chunks_in_course(session, [chunk.chunk_id for chunk in chunks], course)
    # Compiled before the job is queued so an unusable sheet reports the fixable
    # problem now, not as a failed job later.
    planned = compile_chunk_requests(chunks)
    curriculum_version_id = payload.curriculum_version_id or approved_curriculum_id(session, course)

    sheet = payload.model_copy(update={"curriculum_version_id": curriculum_version_id})
    return queue_bulk_generation(session, course, sheet, queue, total=len(planned))


def queue_bulk_generation(
    session: Session,
    course: int | None,
    sheet: GenerateBatchRequest,
    queue: JobQueue,
    *,
    total: int,
    start_at: int = 0,
    retry: bool = False,
) -> JobStartedResponse:
    """Add the job and hand it to the queue. ``start_at`` > 0 resumes a stopped run's plan."""
    plural = "s" if total != 1 else ""
    job = create_job(
        session,
        kind=JobKind.BULK_GENERATION,
        title=f"Bulk generate · {total} question{plural}{' (retry)' if retry else ''}",
        total=total,
        request={"sheet": sheet.model_dump(mode="json"), "start_at": start_at},
        course_id=course,
        run_id=new_run_id(),
    )
    session.commit()
    queue.submit(run_bulk_generation, job.id)
    return JobStartedResponse(job_id=f"job-{job.id}")


def retry_bulk_generation(
    session: Session, course: int | None, job: BackgroundJobRow, queue: JobQueue
) -> JobStartedResponse:
    """Queue the questions a stopped bulk run had not reached, as a new job."""
    remaining = job.total - job.done
    if remaining <= 0:
        raise DomainRuleError("Every question of this run was made.", detail="Nothing to retry.")
    sheet = _sheet_of(job)
    return queue_bulk_generation(
        session,
        course,
        sheet,
        queue,
        total=remaining,
        start_at=int(job.request.get("start_at", 0)) + job.done,
        retry=True,
    )


def _sheet_of(job: BackgroundJobRow) -> GenerateBatchRequest:
    """The spec sheet a bulk job was queued with.

    Stored as ``{"sheet": ..., "start_at": n}``; a job queued before ``start_at`` existed
    stored the sheet itself, and reads as a run from the start.
    """
    return GenerateBatchRequest.model_validate(job.request.get("sheet", job.request))


def run_bulk_generation(job_id: int, *, session_factory=None) -> None:
    """Background body of ``POST /generate-batch``: generate, then store the old response."""
    execute(job_id, _bulk_generation, session_factory=session_factory)


def _bulk_generation(session: Session, job: BackgroundJobRow, progress: Progress) -> dict:
    sheet = _sheet_of(job)
    start_at = int(job.request.get("start_at", 0))
    chunks = [chunk.to_request() for chunk in sheet.chunks]
    planned = compile_chunk_requests(chunks)[start_at:]
    assert sheet.curriculum_version_id is not None
    # Looked up on the module per run, so tests can replace the service.
    generated = GenerationService(session).generate_batch(
        curriculum_version_id=sheet.curriculum_version_id,
        chunks=chunks,
        seed=sheet.seed,
        run_id=job.run_id,
        on_question=progress,
        start_at=start_at,
    )
    return GenerateBatchResponse(
        created=len(generated),
        question_ids=[row.id for row in generated],
        questions=[QuestionSummary.from_row(row) for row in generated],
        planned=[PlannedQuestionOut.from_planned(question) for question in planned],
    ).model_dump(mode="json")


def queue_regeneration(
    session: Session,
    course: int | None,
    question_id: int,
    *,
    feedback: str,
    professor_id: int | None,
    queue: JobQueue,
) -> JobStartedResponse:
    """Check the source question can be regenerated, then queue the regeneration as a job."""
    source = question_in_course(session, question_id, course)
    # Refused now, not as a failed job: no single source chunk, or a superseded curriculum.
    spec = regeneration_spec(session, source)
    require_approved_version(session, spec.curriculum_version_id)
    job = create_job(
        session,
        kind=JobKind.REGENERATION,
        title=f"Regenerate question {question_id}",
        total=1,
        request={"question_id": question_id, "feedback": feedback, "professor_id": professor_id},
        course_id=course,
        run_id=new_run_id(),
    )
    session.commit()
    queue.submit(run_regeneration, job.id)
    return JobStartedResponse(job_id=f"job-{job.id}")


def run_regeneration(job_id: int, *, session_factory=None) -> None:
    """Background body of a ``regenerate`` run; stores the old ``/regenerate`` response."""
    execute(job_id, _regeneration, session_factory=session_factory)


def _regeneration(session: Session, job: BackgroundJobRow, progress: Progress) -> dict:
    request = job.request
    question_id = int(request["question_id"])
    # Looked up on the module per run, so tests can replace the service.
    new_row = GenerationService(session).regenerate_from_question(
        question_id,
        feedback=request["feedback"],
        professor_id=request.get("professor_id"),
        run_id=job.run_id,
    )
    progress()
    return RegenerateQuestionResponse(
        question_id=new_row.id,
        regenerated_from_question_id=question_id,
        question=QuestionSummary.from_row(new_row),
    ).model_dump(mode="json")


def approved_curriculum_id(session: Session, course: int | None = None) -> int:
    """Return the course's approved curriculum id or raise an actionable generation error."""
    approved = CurriculumRepository(session).get_approved(course_id=course)
    if approved is None:
        raise InvalidQuestionSpecError(
            "No approved curriculum is available.",
            detail="Upload a valid taxonomy before generating questions.",
        )
    return approved.id


@router.get("/review-queue", response_model=ReviewQueueResponse)
def review_queue(
    session: DbSession,
    course: CourseScope,
    after: int | None = None,
    mode: ReviewQueueMode = "all",
    curriculum_version_id: int | None = None,
) -> ReviewQueueResponse:
    """The next question awaiting a professor verdict, plus progress counts.

    The queue holds no state. ``after`` is a plain cursor over question ids,
    which is what lets a professor skip a question -- and lets a submitted
    review advance to the next one -- without a stored position per professor.

    Questions that failed deterministic validation are never offered (ADR-032),
    and ``total`` counts only reviewable ones, so a completed pass reads as
    ``remaining == 0`` rather than stalling on questions the queue excludes.
    """
    if curriculum_version_id is not None and course is not None:
        version_in_course(session, curriculum_version_id, course)
    repo = QuestionRepository(session)
    scoreable = [
        row
        for row in repo.list_unreviewed(
            require_evaluation=True, course_id=course, curriculum_version_id=curriculum_version_id
        )
        if _is_scoreable(row)
    ]

    candidates = repo.list_unreviewed(
        after_id=after,
        require_evaluation=mode == "scoreable",
        course_id=course,
        curriculum_version_id=curriculum_version_id,
    )
    if mode == "scoreable":
        candidates = [row for row in candidates if _is_scoreable(row)]

    total = repo.count_reviewable(course_id=course, curriculum_version_id=curriculum_version_id)
    reviewed = repo.count_reviewed(course_id=course, curriculum_version_id=curriculum_version_id)
    return ReviewQueueResponse(
        mode=mode,
        total=total,
        reviewed=reviewed,
        remaining=total - reviewed,
        scoreable_remaining=len(scoreable),
        question=get_question(session, course, candidates[0].id) if candidates else None,
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
def get_question(session: DbSession, course: CourseScope, question_id: int) -> QuestionDetail:
    """One question with its validation report, judge evaluation and provenance."""
    question = question_in_course(session, question_id, course)
    history = QuestionEvaluationRepository(session).list_for_question(question.id)
    current = next((row for row in history if row.evaluation == question.pedagogical_eval), None)
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
        custom_results=(current.custom_results or []) if current is not None else [],
        judge_trust=(
            judge_trust(
                session, question, custom_results=(current.custom_results or []) if current else []
            )
            if question.style_id is not None
            else None
        ),
        pedagogical_error_message=(
            humanize_judge_error_detail(evaluation.error_detail)
            if evaluation is not None and evaluation.status is PedagogicalEvalStatus.ERROR
            else None
        ),
        personalization=personalization_evidence(question),
        original_prompt=question.original_prompt,
        original_reference_solution=question.original_reference_solution,
        original_tests=question.original_tests,
        original_figure=question.original_figure,
        reviews=[ReviewOut.from_row(review) for review in question.reviews],
        borderline_notes=_borderline_notes(question, evaluation),
        figure_copies=[
            FigureCopyOut(
                ordinal=variant.ordinal,
                seed=variant.seed,
                prompt=variant.prompt,
                reference_solution=variant.reference_solution,
                content=variant.content,
            )
            for variant in variants_of(session, question.id)
        ],
        figure_program=question.figure_program,
    )


@router.post("/{question_id}/copies/{ordinal}/regenerate", response_model=QuestionDetail)
def regenerate_figure_copy(
    session: DbSession, course: CourseScope, question_id: int, ordinal: int
) -> QuestionDetail:
    """Replace one copy of a computed-figure question by its program at a new seed (ADR-080).

    No model call: the stored program runs again. A copy a student was served is kept.
    """
    question_in_course(session, question_id, course)
    try:
        regenerate_copy(session, question_id, ordinal)
    except ExecutorError as error:
        session.rollback()
        raise CodeExecutionUnavailableError(
            "Figure programs could not be run right now.", detail=str(error)
        ) from error
    except Exception:
        session.rollback()
        raise
    session.commit()
    return get_question(session, course, question_id)


def resolve_taxonomy(session: Session, question: QuestionRow) -> QuestionTaxonomy:
    """Turn the ids on a question into display names, falling back to the id.

    A question keeps working after its curriculum version is superseded, so a
    name that can no longer be resolved degrades to an em dash rather than 404.
    """
    subtopic_ids = list(question.subtopic_ids)
    taxonomy = QuestionTaxonomy(
        curriculum=str(question.curriculum_version_id or "â€”"),
        topic=str(question.topic_id or "â€”"),
        subtopics=[str(subtopic_id) for subtopic_id in subtopic_ids] or ["â€”"],
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


def _borderline_notes(question: QuestionRow, evaluation: PedagogicalEvaluation | None) -> list[str]:
    spec = question.spec if isinstance(question.spec, dict) else {}
    try:
        requested = Difficulty(spec.get("difficulty") or question.difficulty)
    except ValueError:
        requested = question.difficulty
    target = question.target_subtopic_id
    if target is None:
        return []
    return borderline_notes(evaluation, requested_difficulty=requested, target_subtopic_id=target)
