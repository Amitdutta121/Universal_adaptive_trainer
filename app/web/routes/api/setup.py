"""Question setup: the style library, the AI-suggested setup, and saving it.

Phase 0 contract (docs/QUESTION_SETUP_PLAN.md): paths, request and response models are
fixed; every handler answers 501 until agent A implements it. Saving a setup starts round 1
in the background (``app.generation.rounds.start_round`` then ``run_round``) and returns at
once -- the ``/api/*`` proxy would time out on a synchronous round.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, status

from app.errors import FeatureNotAvailableError
from app.web.routes.api.deps import CourseProfile, DbSession
from app.web.routes.api.schemas import (
    CurrentSetupResponse,
    SaveSetupRequest,
    SaveSetupResponse,
    SetupSuggestionResponse,
    StyleListResponse,
    SuggestSetupRequest,
)

router = APIRouter(tags=["question-setup"])


def _not_yet(what: str) -> FeatureNotAvailableError:
    return FeatureNotAvailableError(f"{what} is not implemented yet (question setup, Phase 1).")


@router.get("/styles", response_model=StyleListResponse)
def list_styles(profile: CourseProfile, subject: str | None = None) -> StyleListResponse:
    """The style library of ``subject``, or of the course's subject when omitted."""
    raise _not_yet("The style library")


@router.post("/setup/suggest", response_model=SetupSuggestionResponse)
def suggest(session: DbSession, body: SuggestSetupRequest) -> SetupSuggestionResponse:
    """AI-suggested styles per subtopic and a target per cell. Persists nothing."""
    raise _not_yet("Setup suggestion")


@router.get("/setup", response_model=CurrentSetupResponse)
def current_setup(session: DbSession, curriculum_version_id: int) -> CurrentSetupResponse:
    """The newest saved setup of a taxonomy, with its newest round; ``setup`` is null if none."""
    raise _not_yet("Reading the setup")


@router.post("/setup", response_model=SaveSetupResponse, status_code=status.HTTP_201_CREATED)
def save_setup(
    session: DbSession, body: SaveSetupRequest, background: BackgroundTasks
) -> SaveSetupResponse:
    """Save the approved setup and start round 1 in the background."""
    raise _not_yet("Saving the setup")
