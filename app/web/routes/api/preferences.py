"""Preference endpoints: inspect and correct what the system inferred.

Refresh is manual and never runs on every review (ADR-025). The professor stays
the authority: confirm raises a statement's confidence, correct rewrites it, and
remove deactivates it without deleting the review history it was drawn from.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.persistence.repositories import PreferenceRepository
from app.personalization import (
    confirm_preference,
    correct_preference,
    refresh_preferences,
    remove_preference,
)
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    CorrectPreferenceRequest,
    PreferenceListResponse,
    PreferenceOut,
    PreferenceRefreshResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/preferences", tags=["preferences"])


def _listing(session: DbSession) -> PreferenceListResponse:
    rows = PreferenceRepository(session).list_all()
    return PreferenceListResponse(
        preferences=[PreferenceOut.from_row(row) for row in rows],
        total=len(rows),
        active_count=sum(1 for row in rows if row.active),
    )


@router.get("", response_model=PreferenceListResponse)
def list_preferences(session: DbSession) -> PreferenceListResponse:
    """Every inferred preference statement, active or not."""
    return _listing(session)


@router.post("/refresh", response_model=PreferenceRefreshResponse)
def refresh(session: DbSession) -> PreferenceRefreshResponse:
    """Re-infer preferences from recent reviews. Requires a configured LLM."""
    try:
        count = refresh_preferences(session)
    except Exception:
        session.rollback()
        raise
    return PreferenceRefreshResponse(
        refreshed=count,
        preferences=_listing(session).preferences,
    )


@router.post("/{preference_id}/confirm", response_model=PreferenceOut)
def confirm(session: DbSession, preference_id: int) -> PreferenceOut:
    """Endorse a statement, which raises its confidence."""
    return PreferenceOut.from_row(confirm_preference(session, preference_id))


@router.post("/{preference_id}/correct", response_model=PreferenceOut)
def correct(
    session: DbSession, preference_id: int, payload: CorrectPreferenceRequest
) -> PreferenceOut:
    """Rewrite a statement's rule text in the professor's own words."""
    try:
        return PreferenceOut.from_row(correct_preference(session, preference_id, payload.rule_text))
    except Exception:
        session.rollback()
        raise


@router.post("/{preference_id}/remove", response_model=PreferenceOut)
def remove(session: DbSession, preference_id: int) -> PreferenceOut:
    """Deactivate a statement so it stops influencing generation."""
    return PreferenceOut.from_row(remove_preference(session, preference_id))
