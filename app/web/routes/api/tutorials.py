"""Tutorial recipes and generated tutorial blocks (Phase 5).

``GET /tutorial-recipes`` lists the course subject's recipes. ``POST /tutorial-blocks``
generates one block of a recipe for a subtopic -- one model call on the ``tutorials`` model
role, plus the recipe's tool and checks -- and saves it as a draft, or as failed with the
reason. ``GET /tutorial-blocks`` lists a subtopic's (or a taxonomy's) bank blocks, newest
first; rejected blocks are hidden. ``PUT /tutorial-recipes/{id}/decision`` approves or rejects a
recipe for a taxonomy, and with it the recipe's blocks there (Phase 6, Task 24).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select

from app.domain.enums import TutorialBlockStatus
from app.errors import DomainRuleError
from app.jobs.queue import JobQueueDep
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import TutorialBlockRow
from app.persistence.repositories import CurriculumRepository
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever
from app.settings_store import ModelRole
from app.tutorials.approval import decide_recipe, decisions, subtopic_ids_of
from app.tutorials.generator import (
    MAX_ATTEMPTS,
    BlockRequest,
    generate_block,
    get_recipe,
    get_recipes,
)
from app.tutorials.jobs import plan_pregeneration, queue_pregeneration
from app.web.routes.api.deps import (
    SPENDS_LLM_CREDIT,
    CourseProfile,
    CourseScope,
    DbSession,
    ensure_in_course,
)
from app.web.routes.api.retrieval import EmbedderDep, get_query_embedder
from app.web.routes.api.schemas import (
    GenerateTutorialBlockRequest,
    JobStartedResponse,
    PlannedTutorialBlock,
    TutorialBlockOut,
    TutorialPregenerationPlan,
    TutorialPregenerationRequest,
    TutorialRecipeDecisionOut,
    TutorialRecipeDecisionRequest,
    TutorialRecipeListResponse,
)

router = APIRouter(tags=["tutorials"])


def get_tutorial_client() -> StructuredLLMClient:
    """The structured client tutorial blocks are written with. Tests override it."""
    return get_structured_client(role=ModelRole.TUTORIALS)


TutorialClientDep = Annotated[StructuredLLMClient, Depends(get_tutorial_client)]


def _subtopic_in_course(session: DbSession, subtopic_id: int, course: int | None) -> None:
    subtopic = CurriculumRepository(session).get_subtopic(subtopic_id)
    ensure_in_course(subtopic.topic.curriculum_version.course_id, course, f"Subtopic {subtopic_id}")


def _version_in_course(session: DbSession, curriculum_version_id: int, course: int | None) -> None:
    version = CurriculumRepository(session).get_version(curriculum_version_id)
    ensure_in_course(version.course_id, course, f"Curriculum version {curriculum_version_id}")


@router.get("/tutorial-recipes", response_model=TutorialRecipeListResponse)
def list_recipes(
    session: DbSession,
    course: CourseScope,
    profile: CourseProfile,
    curriculum_version_id: int | None = None,
) -> TutorialRecipeListResponse:
    """The tutorial recipes of the course's subject (shipped content, not course data), with
    the taxonomy's decisions when ``curriculum_version_id`` is given."""
    decided: dict[str, bool] = {}
    if curriculum_version_id is not None:
        _version_in_course(session, curriculum_version_id, course)
        decided = decisions(session, curriculum_version_id)
    return TutorialRecipeListResponse(
        subject=profile.storage_key, recipes=get_recipes(profile.storage_key), decisions=decided
    )


@router.put("/tutorial-recipes/{recipe_id}/decision", response_model=TutorialRecipeDecisionOut)
def decide(
    session: DbSession,
    course: CourseScope,
    profile: CourseProfile,
    recipe_id: str,
    body: TutorialRecipeDecisionRequest,
) -> TutorialRecipeDecisionOut:
    """Approve or reject a recipe for a taxonomy: its bank blocks there follow, and so do the
    blocks it makes later. Rejected blocks are hidden; only approved ones are frozen."""
    get_recipe(profile.storage_key, recipe_id)
    _version_in_course(session, body.curriculum_version_id, course)
    changed = decide_recipe(
        session,
        curriculum_version_id=body.curriculum_version_id,
        recipe_id=recipe_id,
        approved=body.approved,
    )
    session.commit()
    return TutorialRecipeDecisionOut(
        recipe_id=recipe_id,
        curriculum_version_id=body.curriculum_version_id,
        approved=body.approved,
        blocks_changed=changed,
    )


@router.post(
    "/tutorial-blocks",
    response_model=TutorialBlockOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=SPENDS_LLM_CREDIT,
)
def create_block(
    session: DbSession,
    course: CourseScope,
    embedder: EmbedderDep,
    client: TutorialClientDep,
    body: GenerateTutorialBlockRequest,
) -> TutorialBlockRow:
    """Generate one block. A block that stayed invalid comes back ``failed`` with ``error``."""
    _subtopic_in_course(session, body.subtopic_id, course)
    block = generate_block(
        session,
        BlockRequest(
            subtopic_id=body.subtopic_id,
            recipe_id=body.recipe_id,
            guidance_level=body.guidance_level,
            code=body.code,
        ),
        client=client,
        retriever=ChunkRetriever(session, ChunkEmbeddingStore(session, embedder)),
    )
    session.commit()
    return block


@router.post(
    "/tutorial-pregeneration",
    response_model=JobStartedResponse | TutorialPregenerationPlan,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=SPENDS_LLM_CREDIT,
)
def pregenerate(
    session: DbSession,
    course: CourseScope,
    profile: CourseProfile,
    queue: JobQueueDep,
    body: TutorialPregenerationRequest,
    request: Request,
    response: Response,
) -> JobStartedResponse | TutorialPregenerationPlan:
    """Queue every block the taxonomy's bank is missing, or with ``dry_run`` price it for free.

    Progress and the outcome are in ``GET /api/jobs``, like a generation run.
    """
    _version_in_course(session, body.curriculum_version_id, course)
    for recipe_id in body.recipe_ids or []:
        get_recipe(profile.storage_key, recipe_id)
    planned, existing = plan_pregeneration(session, body.curriculum_version_id, body.recipe_ids)
    if body.dry_run:
        response.status_code = status.HTTP_200_OK
        return TutorialPregenerationPlan(
            planned=[PlannedTutorialBlock.model_validate(p, from_attributes=True) for p in planned],
            blocks_to_create=len(planned),
            already_made=existing,
            generation_calls=len(planned),
            max_attempts_per_block=MAX_ATTEMPTS,
        )
    if not planned:
        raise DomainRuleError(
            "Every tutorial block of this taxonomy is already made.",
            detail="Failed blocks are planned again; approve or reject the recipes below.",
        )
    overrides = request.app.dependency_overrides
    job = queue_pregeneration(
        session,
        course=course,
        curriculum_version_id=body.curriculum_version_id,
        planned=planned,
        queue=queue,
        # Test overrides only; in production the job builds both when it runs.
        client=overrides[get_tutorial_client]() if get_tutorial_client in overrides else None,
        embedder=overrides[get_query_embedder]() if get_query_embedder in overrides else None,
    )
    return JobStartedResponse(job_id=f"job-{job.id}")


@router.get("/tutorial-blocks", response_model=list[TutorialBlockOut])
def list_blocks(
    session: DbSession,
    course: CourseScope,
    subtopic_id: int | None = None,
    curriculum_version_id: int | None = None,
    recipe_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[TutorialBlockRow]:
    """A subtopic's or a taxonomy's bank blocks, newest first, optionally of one recipe.

    Rejected blocks are hidden, and so are the copies frozen with a question set.
    """
    if subtopic_id is None and curriculum_version_id is None:
        raise DomainRuleError("Name a subtopic_id or a curriculum_version_id.")
    stmt = select(TutorialBlockRow).where(
        TutorialBlockRow.set_version_id.is_(None),
        TutorialBlockRow.status != TutorialBlockStatus.REJECTED,
    )
    if subtopic_id is not None:
        _subtopic_in_course(session, subtopic_id, course)
        stmt = stmt.where(TutorialBlockRow.subtopic_id == subtopic_id)
    if curriculum_version_id is not None:
        _version_in_course(session, curriculum_version_id, course)
        stmt = stmt.where(TutorialBlockRow.subtopic_id.in_(subtopic_ids_of(curriculum_version_id)))
    if recipe_id is not None:
        stmt = stmt.where(TutorialBlockRow.recipe_id == recipe_id)
    return list(session.scalars(stmt.order_by(TutorialBlockRow.id.desc()).limit(limit)))
