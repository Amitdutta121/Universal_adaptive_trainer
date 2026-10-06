"""Coverage of the taxonomy by approved questions, and frozen question sets.

Reading a grid is free and changes nothing. Freezing a set writes rows, so it is
a POST the professor triggers deliberately -- and once written, a set is never
edited (ADR-036).

``POST /coverage/generation-runs`` is the exception that does spend model calls:
it retrieves the textbook section that best teaches each selected gap (see
:mod:`app.retrieval`), generates one grounded question from it through the
existing :class:`~app.generation.GenerationService`, and reports what the
generator classified each question as. It runs as a background job
(:mod:`app.jobs`): the request checks and queues it, and ``GET /api/jobs``
reports it. A run cannot be *aimed* -- the generator picks its own topic and
subtopics (ADR-031) -- so the result names the requested subtopic and the
claimed one side by side rather than pretending they always agree.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coverage import (
    build_coverage_report,
    create_question_set,
    sync_prod_question_set,
    sync_taxonomy_question_set,
    taxonomy_alias,
)
from app.domain.enums import JobKind, QuestionType, RoundStatus
from app.errors import DomainRuleError, LLMRequestError, MalformedModelOutputError
from app.evaluation import new_run_id
from app.generation import ChunkQuestionRequest, GenerationService
from app.jobs.queue import JobQueue, JobQueueDep
from app.jobs.runner import Progress, create_job, execute
from app.llm import StructuredLLMClient
from app.persistence.models import BackgroundJobRow, CurriculumVersionRow
from app.persistence.repositories import CurriculumRepository, QuestionSetRepository
from app.retrieval import SectionEmbeddingStore, SectionRetriever
from app.retrieval.embedder import Embedder
from app.web.routes.api.dedup import flag_possible_duplicates
from app.web.routes.api.deps import (
    SPENDS_LLM_CREDIT,
    CourseScope,
    DbSession,
    ensure_in_course,
    ensure_question_types_allowed,
    subtopics_in_course,
)
from app.web.routes.api.questions import approved_curriculum_id
from app.web.routes.api.retrieval import EmbedderDep, get_query_embedder
from app.web.routes.api.schemas import (
    CoverageReportResponse,
    CoverageTargetRef,
    CreateQuestionSetRequest,
    FailedRunTarget,
    FillGapsRequest,
    GeneratedRunQuestion,
    GenerationRunResponse,
    JobStartedResponse,
    QuestionSetListResponse,
    QuestionSetOut,
    SkippedRunTarget,
    TaxonomyLinkListResponse,
    TaxonomyLinkOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["coverage"])

#: A retrieved section below this cosine score is treated as "nothing confident
#: enough to generate from", and its target is skipped rather than producing a
#: question grounded in a section that does not actually teach the subtopic. On
#: the taxonomy benchmark a genuinely on-topic section scores ~0.6 and an
#: unrelated one well under 0.2 (coverage Generate m1). Uncalibrated: revisit
#: once real runs show where the honest hits fall.
MIN_SECTION_SCORE = 0.25


def active_generation_topic_ids(session: Session, course: int | None) -> list[int]:
    """Topic ids with a coverage fill queued or running.

    Read by ``GET /coverage`` so the button can rehydrate its "generating" state after a
    reload, and by the start route to refuse a second, overlapping run on the same gaps.
    Read from the jobs table, so it survives a restart (when the run is marked failed).
    """
    stmt = select(BackgroundJobRow.request).where(
        BackgroundJobRow.kind == JobKind.COVERAGE_FILL,
        BackgroundJobRow.status.in_([RoundStatus.QUEUED, RoundStatus.RUNNING]),
    )
    if course is not None:
        stmt = stmt.where(BackgroundJobRow.course_id == course)
    topic_ids: set[int] = set()
    for request in session.scalars(stmt):
        topic_ids.update((request or {}).get("topic_ids", []))
    return sorted(topic_ids)


def get_generation_client() -> StructuredLLMClient | None:
    """The structured client generation runs on. ``None`` lets the service build
    its own from settings; tests override this with a fake."""
    return None


GenerationClientDep = Annotated[StructuredLLMClient | None, Depends(get_generation_client)]


@router.get("/coverage", response_model=CoverageReportResponse)
def coverage(
    session: DbSession, course: CourseScope, set_version_id: int | None = None
) -> CoverageReportResponse:
    """The subtopic x difficulty grid over approved questions.

    Without ``set_version_id`` this is the live bank -- what to generate next.
    With one it is that frozen set -- what a training run would actually serve.
    """
    if set_version_id is not None:
        _set_in_course(session, set_version_id, course)
    return CoverageReportResponse.from_report(
        build_coverage_report(session, set_version_id=set_version_id, course_id=course),
        active_run_topic_ids=active_generation_topic_ids(session, course),
    )


@router.post(
    "/coverage/generation-runs",
    response_model=JobStartedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=SPENDS_LLM_CREDIT,
)
def start_generation_run(
    session: DbSession,
    course: CourseScope,
    payload: FillGapsRequest,
    embedder: EmbedderDep,
    client: GenerationClientDep,
    queue: JobQueueDep,
) -> JobStartedResponse:
    """Queue one grounded question for each selected coverage gap, as a background job.

    For every target the job retrieves the top book section that teaches its subtopic,
    generates one multiple-choice question from it at the requested difficulty, and
    records what the generator claimed it wrote for (:func:`run_generation_for_gaps`).
    Everything that can be refused is checked here, before the ``202``, including a
    topic that already has a run in flight.
    """
    return queue_coverage_fill(
        session, course, payload.targets, embedder=embedder, client=client, queue=queue
    )


def queue_coverage_fill(
    session: Session,
    course: int | None,
    targets: list[CoverageTargetRef],
    *,
    embedder: Embedder | None,
    client: StructuredLLMClient | None,
    queue: JobQueue,
    retry: bool = False,
) -> JobStartedResponse:
    """Check a set of gap targets, then add their job and hand it to the queue.

    ``embedder`` ``None`` lets the job build the default one when it runs.
    """
    subtopics_in_course(session, [target.subtopic_id for target in targets], course)
    # Resolved before queueing: an unapproved curriculum or an unknown subtopic must
    # report the fixable problem, not a failed job later. Gap filling writes
    # multiple-choice questions, so the course must use them.
    ensure_question_types_allowed(session, course, [QuestionType.MULTIPLE_CHOICE.value])
    approved_curriculum_id(session, course)
    curriculum = CurriculumRepository(session)
    topic_ids = sorted({curriculum.get_subtopic(target.subtopic_id).topic_id for target in targets})
    if set(topic_ids) & set(active_generation_topic_ids(session, course)):
        raise DomainRuleError(
            "This topic is already generating.",
            detail="Wait for its run to finish in Jobs, then fill the gaps that are left.",
        )
    count = len(targets)
    plural = "s" if count != 1 else ""
    job = create_job(
        session,
        kind=JobKind.COVERAGE_FILL,
        title=f"Fill {count} coverage gap{plural}{' (retry)' if retry else ''}",
        total=count,
        request={
            "targets": [target.model_dump(mode="json") for target in targets],
            "topic_ids": topic_ids,
        },
        course_id=course,
        run_id=new_run_id(),
    )
    session.commit()
    queue.submit(run_coverage_fill, job.id, client=client, embedder=embedder)
    return JobStartedResponse(job_id=f"job-{job.id}")


def coverage_retry_targets(job: BackgroundJobRow) -> list[CoverageTargetRef]:
    """The gaps a retry of this coverage fill should try again.

    A run that stopped (failed or cancelled) never reached the targets after ``done``. A run
    that finished may still have lost some to a provider error, listed in its result.
    """
    targets = [
        CoverageTargetRef.model_validate(raw) for raw in (job.request or {}).get("targets", [])
    ]
    if RoundStatus(job.status) is not RoundStatus.DONE:
        return targets[job.done :]
    failed = (job.result or {}).get("failed", [])
    return [
        CoverageTargetRef(subtopic_id=item["subtopic_id"], difficulty=item["difficulty"])
        for item in failed
    ]


def run_coverage_fill(
    job_id: int,
    *,
    client: StructuredLLMClient | None = None,
    embedder: Embedder | None = None,
    session_factory=None,
) -> None:
    """Background body of ``POST /coverage/generation-runs``; stores the old response."""

    def body(session: Session, job: BackgroundJobRow, progress: Progress) -> dict:
        targets = [CoverageTargetRef.model_validate(raw) for raw in job.request["targets"]]
        return run_generation_for_gaps(
            session,
            targets,
            embedder=embedder if embedder is not None else get_query_embedder(),
            client=client,
            course_id=job.course_id,
            run_id=job.run_id,
            on_target=progress,
        ).model_dump(mode="json")

    execute(job_id, body, session_factory=session_factory)


def _set_in_course(session: Session, set_version_id: int, course: int | None) -> None:
    """404 when a frozen question set belongs to another course than the request's."""
    qset = QuestionSetRepository(session).get(set_version_id)
    version = (
        CurriculumRepository(session).get_version(qset.curriculum_version_id)
        if qset.curriculum_version_id is not None
        else None
    )
    ensure_in_course(
        version.course_id if version else None, course, f"Question set {set_version_id}"
    )


def run_generation_for_gaps(
    session: Session,
    targets: list[CoverageTargetRef],
    *,
    embedder: Embedder,
    client: StructuredLLMClient | None,
    course_id: int | None = None,
    run_id: str | None = None,
    on_target: Progress | None = None,
) -> GenerationRunResponse:
    """Wire retrieval to generation for a set of coverage gap targets.

    Kept out of the handler so it can be exercised directly, and off
    :mod:`app.coverage` (which is read-only and must not import the generator).
    ``on_target`` is called once per target handled -- generated, skipped or failed --
    so the job running this can report progress.
    """
    # Resolved before any model call: an unapproved curriculum or an unknown
    # subtopic must report the fixable problem, not leave a partial run behind.
    # Gap filling writes multiple-choice questions, so the course must use them.
    ensure_question_types_allowed(session, course_id, [QuestionType.MULTIPLE_CHOICE.value])
    curriculum_version_id = approved_curriculum_id(session, course_id)
    curriculum = CurriculumRepository(session)
    resolved = [
        (target, curriculum.get_subtopic(target.subtopic_id).topic_id) for target in targets
    ]

    retriever = SectionRetriever(session, SectionEmbeddingStore(session, embedder))
    service = GenerationService(session, client=client)
    run_id = run_id or new_run_id()

    generated: list[GeneratedRunQuestion] = []
    skipped: list[SkippedRunTarget] = []
    failed: list[FailedRunTarget] = []
    possible_duplicates = 0

    for target, requested_topic_id in resolved:
        hits = retriever.for_subtopic(target.subtopic_id, top_k=1)
        if not hits or hits[0].score < MIN_SECTION_SCORE:
            skipped.append(
                SkippedRunTarget(
                    subtopic_id=target.subtopic_id,
                    difficulty=target.difficulty,
                    reason="no confident section",
                )
            )
            if on_target is not None:
                on_target()
            continue

        section_id = hits[0].section_id
        chunk = ChunkQuestionRequest(
            section_id=section_id,
            counts={target.difficulty: 1},
            question_types=(QuestionType.MULTIPLE_CHOICE,),
        )
        try:
            rows = service.generate_batch(
                curriculum_version_id=curriculum_version_id,
                chunks=[chunk],
                run_id=run_id,
            )
        except (LLMRequestError, MalformedModelOutputError) as exc:
            # The questions already committed under this run id stay; only the
            # target in flight is lost.
            session.rollback()
            logger.warning(
                "generation-run %s: provider failed for subtopic %s: %s",
                run_id,
                target.subtopic_id,
                exc.message,
            )
            failed.append(
                FailedRunTarget(
                    subtopic_id=target.subtopic_id,
                    difficulty=target.difficulty,
                    section_id=section_id,
                    error=exc.message,
                )
            )
            if on_target is not None:
                on_target()
            continue

        row = rows[0]
        generated.append(
            GeneratedRunQuestion(
                question_id=row.id,
                requested_subtopic_id=target.subtopic_id,
                requested_difficulty=target.difficulty,
                claimed_topic_id=row.topic_id,
                claimed_subtopic_ids=list(row.subtopic_ids),
                section_id=section_id,
                status=row.status,
                aim_matched=row.topic_id == requested_topic_id,
            )
        )
        try:
            possible_duplicates += flag_possible_duplicates(session, embedder, rows)
        except Exception:
            # A flagging failure must never fail the run it followed -- the
            # questions above are already committed and stay (m3: dedup is a
            # soft flag, never a gate). Rollback clears any half-written
            # QuestionSimilarityRow so the next target starts from a clean
            # session.
            session.rollback()
            logger.warning(
                "generation-run %s: duplicate flagging failed for subtopic %s",
                run_id,
                target.subtopic_id,
                exc_info=True,
            )
        if on_target is not None:
            on_target()

    return GenerationRunResponse(
        run_id=run_id,
        generated=generated,
        skipped=skipped,
        failed=failed,
        possible_duplicates=possible_duplicates,
    )


@router.get("/question-sets", response_model=QuestionSetListResponse)
def list_question_sets(session: DbSession, course: CourseScope) -> QuestionSetListResponse:
    rows = QuestionSetRepository(session).list_versions(course_id=course)
    return QuestionSetListResponse(
        sets=[
            QuestionSetOut.from_row(
                row,
                is_prod=any(alias.alias == "prod" for alias in row.aliases),
            )
            for row in rows
        ],
        total=len(rows),
    )


@router.post(
    "/question-sets",
    response_model=QuestionSetOut,
    status_code=status.HTTP_201_CREATED,
)
def create_set(
    session: DbSession, course: CourseScope, payload: CreateQuestionSetRequest
) -> QuestionSetOut:
    """Freeze every approved question of the course's approved curriculum under a name."""
    row = create_question_set(session, label=payload.label, notes=payload.notes, course_id=course)
    return QuestionSetOut.from_row(row)


@router.post(
    "/question-sets/prod/sync",
    response_model=QuestionSetOut,
    status_code=status.HTTP_201_CREATED,
)
def sync_prod_set(session: DbSession, course: CourseScope) -> QuestionSetOut:
    """Superseded by per-taxonomy links; kept so an existing prod link can still be refreshed."""
    return _sync_prod(session, course)


@router.get("/question-sets/taxonomy-links", response_model=TaxonomyLinkListResponse)
def list_taxonomy_links(session: DbSession, course: CourseScope) -> TaxonomyLinkListResponse:
    """Every taxonomy in the course with its classroom link's current snapshot, if any.

    One call for the whole list, so the Classrooms page does not ask once per taxonomy.
    """
    sets = QuestionSetRepository(session)
    links: list[TaxonomyLinkOut] = []
    for version in CurriculumRepository(session).list_versions(limit=200, course_id=course):
        alias = sets.get_alias(taxonomy_alias(version.id))
        classroom = alias.set_version if alias is not None else None
        links.append(
            TaxonomyLinkOut(
                curriculum_version_id=version.id,
                label=version.label,
                approved_question_count=len(
                    sets.approved_question_ids(curriculum_version_id=version.id)
                ),
                classroom=QuestionSetOut.from_row(classroom) if classroom is not None else None,
            )
        )
    return TaxonomyLinkListResponse(links=links)


@router.post(
    "/question-sets/taxonomy/{curriculum_version_id}/sync",
    response_model=QuestionSetOut,
    status_code=status.HTTP_201_CREATED,
)
def sync_taxonomy_set(
    session: DbSession, course: CourseScope, curriculum_version_id: int
) -> QuestionSetOut:
    """Freeze this taxonomy's approved questions and point its classroom link at them.

    Each taxonomy has its own stable link (``/students/join?taxonomy={id}``), so
    any taxonomy can be taught, not only the selected one.
    """
    version = CurriculumRepository(session).get_version(curriculum_version_id)
    ensure_in_course(version.course_id, course, f"Curriculum version {curriculum_version_id}")
    row = sync_taxonomy_question_set(session, curriculum_version_id)
    return QuestionSetOut.from_row(row)


def _sync_prod(session: DbSession, course: int | None) -> QuestionSetOut:
    """Freeze the approved bank now and repoint the stable prod classroom link.

    There is one ``prod`` alias per installation, so a course may only repoint it while it
    is unset or already serves this course: otherwise one professor could swap another's
    students onto their own bank (ADR-060).
    """
    current = QuestionSetRepository(session).get_alias("prod")
    if current is not None and current.set_version is not None:
        version_id = current.set_version.curriculum_version_id
        version = session.get(CurriculumVersionRow, version_id) if version_id else None
        ensure_in_course(version.course_id if version else None, course, "The prod classroom")
    row = sync_prod_question_set(session, course_id=course)
    return QuestionSetOut.from_row(row, is_prod=True)
