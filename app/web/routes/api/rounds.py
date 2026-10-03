"""Generation rounds: start the next round of a setup, and poll one.

Phase 0 contract (docs/QUESTION_SETUP_PLAN.md): paths and models are fixed; handlers answer
501 until agent B implements them. ``POST`` creates the round (``next_round``), commits, and
schedules ``run_round`` as a background task; the client polls ``GET /rounds/{id}`` until
``status`` is ``done`` or ``failed``.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, status

from app.errors import FeatureNotAvailableError
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import GenerationRoundOut, StartRoundRequest, StartRoundResponse

router = APIRouter(prefix="/rounds", tags=["question-setup"])


@router.post("", response_model=StartRoundResponse, status_code=status.HTTP_202_ACCEPTED)
def start_next_round(
    session: DbSession, body: StartRoundRequest, background: BackgroundTasks
) -> StartRoundResponse:
    """Queue the next round of a setup, for cells still below target."""
    raise FeatureNotAvailableError("Generation rounds are not implemented yet (Phase 1).")


@router.get("/{round_id}", response_model=GenerationRoundOut)
def get_round(session: DbSession, round_id: int) -> GenerationRoundOut:
    """One round's status and progress counters."""
    raise FeatureNotAvailableError("Generation rounds are not implemented yet (Phase 1).")
