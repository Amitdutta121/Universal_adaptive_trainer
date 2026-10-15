"""One endpoint for every professor generation run (ADR-066).

``POST /generation-runs`` takes one target kind and hands it to the pipeline that already
serves it: ``chunks`` and ``gaps`` and ``regenerate`` to the plain pipeline
(``GenerationService._generate_specs``), ``setup_cells`` to the round pipeline
(``app.generation.rounds``). The pipelines are not merged. Every run is queued; ``dry_run``
returns the plan and its call counts without a model call or a written row.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, JudgeMetricId, QuestionType
from app.errors import InvalidQuestionSpecError
from app.generation.attempts import MAX_GENERATION_ATTEMPTS
from app.generation.rounds import plan_targets
from app.generation.service import regeneration_spec
from app.ingestion import SourceRetrieval
from app.jobs.queue import JobQueueDep
from app.persistence.repositories import QuestionSetupRepository
from app.retrieval.embedder import Embedder
from app.web.routes.api.coverage import GenerationClientDep, queue_coverage_fill
from app.web.routes.api.deps import (
    SPENDS_LLM_CREDIT,
    CourseScope,
    DbSession,
    book_in_course,
    question_in_course,
)
from app.web.routes.api.questions import plan_chunk_sheet, queue_chunk_sheet, queue_regeneration
from app.web.routes.api.retrieval import get_query_embedder
from app.web.routes.api.rounds import _ensure_setup_in_course, queue_next_round
from app.web.routes.api.schemas import (
    ChunkGenerationSpec,
    ChunksRunTarget,
    GapsRunTarget,
    GenerateBatchRequest,
    GenerationRunPlan,
    GenerationRunRequest,
    GenerationRunStarted,
    GenerationRunTotals,
    PlannedRunQuestion,
    RegenerateRunTarget,
    SetupCellsRunTarget,
)

router = APIRouter(prefix="/generation-runs", tags=["generation"])

JUDGE_CALLS_PER_QUESTION = len(JudgeMetricId)


@router.post(
    "",
    response_model=GenerationRunStarted | GenerationRunPlan,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=SPENDS_LLM_CREDIT,
)
def start_generation_run(
    session: DbSession,
    course: CourseScope,
    payload: GenerationRunRequest,
    queue: JobQueueDep,
    client: GenerationClientDep,
    request: Request,
    response: Response,
) -> GenerationRunStarted | GenerationRunPlan:
    """Queue a run of one target kind, or with ``dry_run`` plan it for free.

    Everything that can be refused is checked before the ``202``, as on the old routes.
    """
    target = payload.target
    if payload.dry_run:
        response.status_code = status.HTTP_200_OK
    if isinstance(target, ChunksRunTarget):
        sheet = _chunk_sheet(session, course, target)
        if payload.dry_run:
            return _chunks_plan(sheet)
        started = queue_chunk_sheet(session, course, sheet, queue)
        return GenerationRunStarted(kind=target.kind, job_id=started.job_id)
    if isinstance(target, GapsRunTarget):
        if payload.dry_run:
            return _gaps_plan(target)
        started = queue_coverage_fill(
            session,
            course,
            target.targets,
            embedder=_query_embedder(request),
            client=client,
            queue=queue,
        )
        return GenerationRunStarted(kind=target.kind, job_id=started.job_id)
    if isinstance(target, SetupCellsRunTarget):
        if payload.dry_run:
            return _setup_cells_plan(session, course, target)
        round_started = queue_next_round(
            session, course, target.setup_id, target.size, queue, client
        )
        return GenerationRunStarted(
            kind=target.kind,
            job_id=f"round-{round_started.round_id}",
            round_id=round_started.round_id,
        )
    # The only kind left: the union is closed (ADR-066).
    assert isinstance(target, RegenerateRunTarget)
    if payload.dry_run:
        return _regenerate_plan(session, course, target)
    started = queue_regeneration(
        session,
        course,
        target.question_id,
        feedback=target.feedback,
        professor_id=target.professor_id,
        queue=queue,
    )
    return GenerationRunStarted(kind=target.kind, job_id=started.job_id)


def _query_embedder(request: Request) -> Embedder:
    """The query embedder, built only for the kinds that retrieve.

    Not a route dependency: building it fails without an embedder configured, and a
    ``chunks`` run must not need one. Test overrides of ``get_query_embedder`` still apply.
    """
    factory = request.app.dependency_overrides.get(get_query_embedder, get_query_embedder)
    return factory()


def _chunk_sheet(
    session: Session, course: int | None, target: ChunksRunTarget
) -> GenerateBatchRequest:
    """The spec sheet a ``chunks`` target asks for, with a whole book expanded per chunk."""
    chunks: list[ChunkGenerationSpec] = list(target.chunks)
    if target.whole_book is not None:
        book_in_course(session, target.whole_book.book_id, course)
        chunks = [
            target.whole_book.for_chunk(chunk.id)
            for chunk in SourceRetrieval(session).chunks_in_book(target.whole_book.book_id)
        ]
        if not chunks:
            raise InvalidQuestionSpecError(
                "This book has no chunks to generate from.",
                detail="Import the book file again, then generate.",
            )
    return GenerateBatchRequest(
        curriculum_version_id=target.curriculum_version_id, chunks=chunks, seed=target.seed
    )


def _gaps_plan(target: GapsRunTarget) -> GenerationRunPlan:
    """One multiple-choice question per gap. No retrieval: that would spend embedder credit."""
    count = len(target.targets)
    return GenerationRunPlan(
        kind=target.kind,
        planned=[
            PlannedRunQuestion(
                subtopic_id=gap.subtopic_id,
                difficulty=gap.difficulty,
                question_type=QuestionType.MULTIPLE_CHOICE,
            )
            for gap in target.targets
        ],
        totals=GenerationRunTotals(
            questions_to_create=count,
            generation_calls=count,
            judge_calls=count * JUDGE_CALLS_PER_QUESTION,
            max_attempts_per_question=MAX_GENERATION_ATTEMPTS,
        ),
    )


def _setup_cells_plan(
    session: Session, course: int | None, target: SetupCellsRunTarget
) -> GenerationRunPlan:
    """The targets the next round would draw. Styles are drawn at random, so the real round
    may pick other styles for the same cells. Empty when every cell has reached its target."""
    _ensure_setup_in_course(session, target.setup_id, course)
    setup = QuestionSetupRepository(session).get(target.setup_id)
    targets = plan_targets(session, setup, size=target.size)
    hard = sum(1 for t in targets if t["difficulty"] == Difficulty.HARD.value)
    return GenerationRunPlan(
        kind=target.kind,
        planned=[
            PlannedRunQuestion(
                subtopic_id=int(t["subtopic_id"]),
                difficulty=Difficulty(t["difficulty"]),
                style_id=str(t["style_id"]),
            )
            for t in targets
        ],
        totals=GenerationRunTotals(
            questions_to_create=len(targets),
            # A hard cell is a medium question first, then a harder one made from it.
            generation_calls=len(targets) + hard,
            judge_calls=None,
            max_attempts_per_question=MAX_GENERATION_ATTEMPTS,
        ),
    )


def _regenerate_plan(
    session: Session, course: int | None, target: RegenerateRunTarget
) -> GenerationRunPlan:
    """One new question in the source's chunk, type and difficulty."""
    source = question_in_course(session, target.question_id, course)
    spec = regeneration_spec(session, source)
    return GenerationRunPlan(
        kind=target.kind,
        planned=[
            PlannedRunQuestion(
                question_id=source.id,
                chunk_id=spec.source_chunk_ids[0],
                difficulty=spec.difficulty,
                question_type=spec.question_type,
            )
        ],
        totals=GenerationRunTotals(
            questions_to_create=1,
            generation_calls=1,
            judge_calls=JUDGE_CALLS_PER_QUESTION,
            max_attempts_per_question=MAX_GENERATION_ATTEMPTS,
        ),
    )


def _chunks_plan(sheet: GenerateBatchRequest) -> GenerationRunPlan:
    plan = plan_chunk_sheet(sheet.chunks)
    return GenerationRunPlan(
        kind="chunks",
        planned=[
            PlannedRunQuestion(
                chunk_id=question.chunk_id,
                difficulty=question.difficulty,
                question_type=question.question_type,
            )
            for question in plan.planned
        ],
        totals=GenerationRunTotals(
            questions_to_create=plan.totals.questions_to_create,
            generation_calls=plan.totals.generation_calls,
            judge_calls=plan.totals.judge_calls,
            max_attempts_per_question=MAX_GENERATION_ATTEMPTS,
            identical_repeats=plan.totals.identical_repeats,
        ),
    )
