"""Tutorial recipes and generated tutorial blocks (Phase 5).

``GET /tutorial-recipes`` lists the course subject's recipes. ``POST /tutorial-blocks``
generates one block of a recipe for a subtopic -- one model call on the ``tutorials`` model
role, plus the recipe's tool and checks -- and saves it as a draft, or as failed with the
reason. ``GET /tutorial-blocks?subtopic_id=`` lists a subtopic's blocks, newest first.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import TutorialBlockRow
from app.persistence.repositories import CurriculumRepository
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever
from app.settings_store import ModelRole
from app.tutorials.generator import BlockRequest, generate_block, get_recipes
from app.web.routes.api.deps import (
    SPENDS_LLM_CREDIT,
    CourseProfile,
    CourseScope,
    DbSession,
    ensure_in_course,
)
from app.web.routes.api.retrieval import EmbedderDep
from app.web.routes.api.schemas import (
    GenerateTutorialBlockRequest,
    TutorialBlockOut,
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


@router.get("/tutorial-recipes", response_model=TutorialRecipeListResponse)
def list_recipes(profile: CourseProfile) -> TutorialRecipeListResponse:
    """The tutorial recipes of the course's subject (shipped content, not course data)."""
    return TutorialRecipeListResponse(
        subject=profile.storage_key, recipes=get_recipes(profile.storage_key)
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


@router.get("/tutorial-blocks", response_model=list[TutorialBlockOut])
def list_blocks(
    session: DbSession, course: CourseScope, subtopic_id: int
) -> list[TutorialBlockRow]:
    """A subtopic's blocks, newest first."""
    _subtopic_in_course(session, subtopic_id, course)
    return list(
        session.scalars(
            select(TutorialBlockRow)
            .where(TutorialBlockRow.subtopic_id == subtopic_id)
            .order_by(TutorialBlockRow.id.desc())
        )
    )
