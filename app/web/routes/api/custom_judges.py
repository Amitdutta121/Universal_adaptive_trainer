"""Custom rule judges of a taxonomy: list, create, edit (enable/disable).

Phase 0 contract (docs/QUESTION_SETUP_PLAN.md): paths and models are fixed; handlers answer
501 until agent C implements them over ``CustomJudgeRepository``.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.errors import FeatureNotAvailableError
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    CreateCustomJudgeRequest,
    CustomJudgeListResponse,
    CustomJudgeOut,
    UpdateCustomJudgeRequest,
)

router = APIRouter(prefix="/custom-judges", tags=["custom-judges"])

_NOT_YET = "Custom judges are not implemented yet (Phase 1)."


@router.get("", response_model=CustomJudgeListResponse)
def list_custom_judges(session: DbSession, curriculum_version_id: int) -> CustomJudgeListResponse:
    """Every custom judge of a taxonomy, enabled or not, oldest first."""
    raise FeatureNotAvailableError(_NOT_YET)


@router.post("", response_model=CustomJudgeOut, status_code=status.HTTP_201_CREATED)
def create_custom_judge(session: DbSession, body: CreateCustomJudgeRequest) -> CustomJudgeOut:
    """Add a rule. A ``pattern`` rule must carry a compilable ``pattern``."""
    raise FeatureNotAvailableError(_NOT_YET)


@router.patch("/{judge_id}", response_model=CustomJudgeOut)
def update_custom_judge(
    session: DbSession, judge_id: int, body: UpdateCustomJudgeRequest
) -> CustomJudgeOut:
    """Change a rule's text, kind, pattern, or enabled flag."""
    raise FeatureNotAvailableError(_NOT_YET)
