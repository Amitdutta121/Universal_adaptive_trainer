"""Judge scorecard: how each judge is doing against the professor (ADR-064, m8).

Read-only. The figures come from reviews and round attempts already stored; this
route never generates, evaluates, or writes.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.calibration import build_judge_scorecard
from app.web.routes.api.deps import CourseScope, DbSession
from app.web.routes.api.schemas import JudgeScorecardResponse

router = APIRouter(prefix="/judges", tags=["judges"])


@router.get("/scorecard", response_model=JudgeScorecardResponse)
def judge_scorecard(session: DbSession, course: CourseScope) -> JudgeScorecardResponse:
    """Agreement, κ, Wilson 95% range, misses, false alarms, flag rate, retries and drops."""
    return JudgeScorecardResponse.from_report(build_judge_scorecard(session, course_id=course))
