"""Calibration endpoints: how far the advisory judge agrees with the professor.

Read-only. The endpoint measures data the professor already produced (ADR-029);
it never triggers generation, evaluation or review, and it stores nothing, so
calling it twice cannot change what the second call reports.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.calibration import build_calibration_pairs, build_calibration_report
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    CalibrationPairOut,
    CalibrationPairsResponse,
    CalibrationResultsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calibration", tags=["calibration"])


@router.get("/results", response_model=CalibrationResultsResponse)
def calibration_results(session: DbSession) -> CalibrationResultsResponse:
    """Judge/professor agreement over every reviewed, judged question."""
    return CalibrationResultsResponse.from_report(build_calibration_report(session))


@router.get("/pairs", response_model=CalibrationPairsResponse)
def calibration_pairs(session: DbSession) -> CalibrationPairsResponse:
    """The questions behind the figures, so a rate can be checked against rows."""
    pairs = build_calibration_pairs(session)
    return CalibrationPairsResponse(
        pairs=[CalibrationPairOut.from_pair(pair) for pair in pairs],
        total=len(pairs),
    )
