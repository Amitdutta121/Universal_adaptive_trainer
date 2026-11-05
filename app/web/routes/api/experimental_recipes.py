"""The experimental recipe builder's API: tutorial recipes drafted with AI, kept per course.

List, create, edit and delete a course's experimental recipes; draft or revise one with the
``tutorials`` model role; and try one -- a single block for a real subtopic, written by the
library's generator and never saved. See ``app/tutorials/experimental.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.persistence.models import ExperimentalRecipeRow
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever
from app.tutorials import experimental
from app.web.routes.api.deps import SPENDS_LLM_CREDIT, CourseProfile, CourseScope, DbSession
from app.web.routes.api.retrieval import EmbedderDep
from app.web.routes.api.schemas import (
    ExperimentalRecipeDraftOut,
    ExperimentalRecipeDraftRequest,
    ExperimentalRecipeOut,
    ExperimentalRecipeTryOut,
    ExperimentalRecipeTryRequest,
    ExperimentalRecipeYaml,
)
from app.web.routes.api.tutorials import TutorialClientDep, _subtopic_in_course

router = APIRouter(prefix="/experimental/recipes", tags=["experimental"])


def _out(profile: CourseProfile, row: ExperimentalRecipeRow) -> ExperimentalRecipeOut:
    recipe = experimental.parse_recipe(row.yaml, profile.storage_key)
    return ExperimentalRecipeOut(
        id=row.id,
        recipe_id=row.recipe_id,
        name=recipe.name,
        summary=recipe.summary,
        renderer=recipe.renderer,
        yaml=row.yaml,
        updated_at=row.updated_at,
        recipe=recipe,
    )


@router.get("", response_model=list[ExperimentalRecipeOut])
def list_recipes(session: DbSession, profile: CourseProfile) -> list[ExperimentalRecipeOut]:
    return [_out(profile, row) for row in experimental.list_recipes(session, profile)]


@router.post("/draft", response_model=ExperimentalRecipeDraftOut, dependencies=SPENDS_LLM_CREDIT)
def draft(
    profile: CourseProfile, client: TutorialClientDep, body: ExperimentalRecipeDraftRequest
) -> ExperimentalRecipeDraftOut:
    """Draft a recipe from the professor's words, or revise ``current_yaml``. Saves nothing."""
    result = experimental.draft_recipe(
        client, profile.storage_key, body.description, body.current_yaml
    )
    return ExperimentalRecipeDraftOut(
        yaml=result.yaml, problems=result.problems, recipe=result.recipe
    )


@router.post("/try", response_model=ExperimentalRecipeTryOut, dependencies=SPENDS_LLM_CREDIT)
def try_recipe(
    session: DbSession,
    course: CourseScope,
    profile: CourseProfile,
    embedder: EmbedderDep,
    client: TutorialClientDep,
    body: ExperimentalRecipeTryRequest,
) -> ExperimentalRecipeTryOut:
    """Write one block of the recipe for a subtopic, without saving the block or the recipe."""
    _subtopic_in_course(session, body.subtopic_id, course)
    block = experimental.try_recipe(
        session,
        profile,
        body.yaml,
        subtopic_id=body.subtopic_id,
        guidance_level=body.guidance_level,
        client=client,
        retriever=ChunkRetriever(session, ChunkEmbeddingStore(session, embedder)),
    )
    # Chunks embedded on the way are worth keeping; the block itself never entered the session.
    session.commit()
    return ExperimentalRecipeTryOut.model_validate(block)


def _store(
    session: DbSession, profile: CourseProfile, body: ExperimentalRecipeYaml, row_id: int | None
) -> ExperimentalRecipeOut:
    stored = experimental.store_recipe(session, profile, body.yaml, row_id)
    kept = experimental.keep_examples(
        session,
        profile,
        body.yaml,
        [experimental.Example(**example.model_dump()) for example in body.examples],
    )
    session.commit()
    return _out(profile, stored.row).model_copy(
        update={"blocks_retired": stored.blocks_retired, "examples_kept": kept}
    )


@router.post("", response_model=ExperimentalRecipeOut, status_code=status.HTTP_201_CREATED)
def create(
    session: DbSession, profile: CourseProfile, body: ExperimentalRecipeYaml
) -> ExperimentalRecipeOut:
    return _store(session, profile, body, None)


@router.put("/{row_id}", response_model=ExperimentalRecipeOut)
def update(
    session: DbSession, profile: CourseProfile, row_id: int, body: ExperimentalRecipeYaml
) -> ExperimentalRecipeOut:
    return _store(session, profile, body, row_id)


@router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(session: DbSession, profile: CourseProfile, row_id: int) -> Response:
    experimental.delete_recipe(session, profile, row_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
