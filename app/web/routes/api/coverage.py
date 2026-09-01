"""Coverage of the taxonomy by approved questions, and frozen question sets.

Reading a grid is free and changes nothing. Freezing a set writes rows, so it is
a POST the professor triggers deliberately -- and once written, a set is never
edited (ADR-036).

``POST /coverage/generation-runs`` is the exception that does spend model calls:
it retrieves the textbook section that best teaches each selected gap (see
:mod:`app.retrieval`), generates one grounded question from it through the
existing :class:`~app.generation.GenerationService`, and reports what the
generator classified each question as. A run cannot be *aimed* -- the generator
picks its own topic and subtopics (ADR-031) -- so the response names the
requested subtopic and the claimed one side by side rather than pretending they
always agree.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.coverage import build_coverage_report, create_question_set, sync_prod_question_set
from app.domain.enums import QuestionType
from app.errors import LLMRequestError, MalformedModelOutputError
from app.evaluation import new_run_id
from app.generation import ChunkQuestionRequest, GenerationService
from app.llm import StructuredLLMClient
from app.persistence.repositories import CurriculumRepository, QuestionSetRepository
from app.retrieval import SectionEmbeddingStore, SectionRetriever
from app.retrieval.embedder import Embedder
from app.web.routes.api.dedup import flag_possible_duplicates
from app.web.routes.api.deps import DbSession
from app.web.routes.api.questions import approved_curriculum_id
from app.web.routes.api.retrieval import EmbedderDep
from app.web.routes.api.schemas import (
    CoverageReportResponse,
    CoverageTargetRef,
    CreateQuestionSetRequest,
    FailedRunTarget,
    FillGapsRequest,
    GeneratedRunQuestion,
    GenerationRunResponse,
    QuestionSetListResponse,
    QuestionSetOut,
    SkippedRunTarget,
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


def get_generation_client() -> StructuredLLMClient | None:
    """The structured client generation runs on. ``None`` lets the service build
    its own from settings; tests override this with a fake."""
    return None


GenerationClientDep = Annotated[StructuredLLMClient | None, Depends(get_generation_client)]


@router.get("/coverage", response_model=CoverageReportResponse)
def coverage(session: DbSession, set_version_id: int | None = None) -> CoverageReportResponse:
    """The subtopic x difficulty grid over approved questions.

    Without ``set_version_id`` this is the live bank -- what to generate next.
    With one it is that frozen set -- what a training run would actually serve.
    """
    return CoverageReportResponse.from_report(
        build_coverage_report(session, set_version_id=set_version_id)
    )


@router.post("/coverage/generation-runs", response_model=GenerationRunResponse)
def start_generation_run(
    session: DbSession,
    payload: FillGapsRequest,
    embedder: EmbedderDep,
    client: GenerationClientDep,
) -> GenerationRunResponse:
    """Generate one grounded question for each selected coverage gap.

    For every target: retrieve the top book section that teaches its subtopic,
    generate one multiple-choice question from that section at the requested
    difficulty, and report what the generator claimed it wrote for. A target
    with no confident section is skipped and the run continues; a provider
    failure on one target is reported beside the questions the run did produce
    (ADR-032). The new questions land in the review queue with no extra step.
    """
    return run_generation_for_gaps(session, payload.targets, embedder=embedder, client=client)


def run_generation_for_gaps(
    session: Session,
    targets: list[CoverageTargetRef],
    *,
    embedder: Embedder,
    client: StructuredLLMClient | None,
) -> GenerationRunResponse:
    """Wire retrieval to generation for a set of coverage gap targets.

    Kept out of the handler so it can be exercised directly, and off
    :mod:`app.coverage` (which is read-only and must not import the generator).
    """
    # Resolved before any model call: an unapproved curriculum or an unknown
    # subtopic must report the fixable problem, not leave a partial run behind.
    curriculum_version_id = approved_curriculum_id(session)
    curriculum = CurriculumRepository(session)
    resolved = [
        (target, curriculum.get_subtopic(target.subtopic_id).topic_id) for target in targets
    ]

    retriever = SectionRetriever(session, SectionEmbeddingStore(session, embedder))
    service = GenerationService(session, client=client)
    run_id = new_run_id()

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

    return GenerationRunResponse(
        run_id=run_id,
        generated=generated,
        skipped=skipped,
        failed=failed,
        possible_duplicates=possible_duplicates,
    )


@router.get("/question-sets", response_model=QuestionSetListResponse)
def list_question_sets(session: DbSession) -> QuestionSetListResponse:
    rows = QuestionSetRepository(session).list_versions()
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
def create_set(session: DbSession, payload: CreateQuestionSetRequest) -> QuestionSetOut:
    """Freeze every approved question of the approved curriculum under a name."""
    row = create_question_set(session, label=payload.label, notes=payload.notes)
    return QuestionSetOut.from_row(row)

@router.post(
    "/question-sets/prod/sync",
    response_model=QuestionSetOut,
    status_code=status.HTTP_201_CREATED,
)
def sync_prod_set(session: DbSession) -> QuestionSetOut:
    """Freeze the approved bank now and repoint the stable prod classroom link."""
    row = sync_prod_question_set(session)
    return QuestionSetOut.from_row(row, is_prod=True)
