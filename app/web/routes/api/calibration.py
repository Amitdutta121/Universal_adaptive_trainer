"""Calibration endpoints: how far the advisory judge agrees with the professor.

Read-only. The endpoint measures data the professor already produced (ADR-029);
it never triggers generation, evaluation or review, and it stores nothing, so
calling it twice cannot change what the second call reports.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.calibration import (
    HELD_OUT_DIVISOR,
    PROFESSOR_OBJECTIONS,
    build_agreement_trend,
    build_calibration_pairs,
    build_calibration_report,
    metrics_from_pairs,
    reports_by_type,
)
from app.domain.enums import JudgeMetricId
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    AgreementTrendResponse,
    CalibrationPairOut,
    CalibrationPairsResponse,
    CalibrationQuadrantResponse,
    CalibrationResultsResponse,
    TypeCalibrationOut,
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


@router.get("/quadrant", response_model=CalibrationQuadrantResponse)
def calibration_quadrant(
    session: DbSession, rubric_version: str | None = None
) -> CalibrationQuadrantResponse:
    """The four-cell breakdown per question type, with the questions in each.

    ``rubric_version`` narrows the pairs to one judge. Without it the response
    reports every version it drew on, so a figure spanning two judges is
    visible rather than implied.
    """
    pairs = build_calibration_pairs(session, rubric_version=rubric_version)
    return CalibrationQuadrantResponse(
        overall=CalibrationResultsResponse.from_report(metrics_from_pairs(pairs)),
        types=[
            TypeCalibrationOut.from_type_calibration(calibration)
            for calibration in reports_by_type(pairs)
        ],
        unattributable_metrics=[
            metric for metric in JudgeMetricId if metric not in PROFESSOR_OBJECTIONS
        ],
        held_out_divisor=HELD_OUT_DIVISOR,
    )


@router.get("/trend", response_model=AgreementTrendResponse)
def agreement_trend(session: DbSession) -> AgreementTrendResponse:
    """Agreement per judge panel, in the order the panels ran (ADR-041).

    The measurement that can falsify ADR-039: a judge rewriting itself from its
    own mistakes is assumed to converge on the professor, and this is what says
    whether it did. Read-only, and built from the frozen ``review_outcomes``
    rows rather than from the live evaluations, which a re-judge overwrites.
    """
    return AgreementTrendResponse.from_trend(build_agreement_trend(session))
