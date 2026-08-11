"""Pedagogical evaluation schema and advisory summary helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.evaluation.rubric import RUBRIC_VERSION, JudgeDimensionId


def _now() -> datetime:
    return datetime.now(UTC)


class DimensionEvaluation(BaseModel):
    dimension: JudgeDimensionId
    score: int | None = Field(default=None, ge=1, le=5)
    applicable: bool = True
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    issues: list[str] = Field(default_factory=list)


class JudgeModelResponse(BaseModel):
    """Structured LLM output only (no provenance / status)."""

    dimensions: list[DimensionEvaluation] = Field(min_length=1)


class PedagogicalEvalStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ERROR = "error"


class AdvisoryStatus(StrEnum):
    STRONG = "strong"
    ADEQUATE = "adequate"
    WEAK = "weak"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"
    ERROR = "error"


class PedagogicalEvaluation(BaseModel):
    question_id: int | None = None
    status: PedagogicalEvalStatus
    skip_reason: str | None = None
    error_detail: str | None = None
    overall_advisory_score: float | None = None
    overall_advisory_status: AdvisoryStatus
    dimensions: list[DimensionEvaluation] = Field(default_factory=list)
    judge_model: str | None = None
    rubric_version: str = RUBRIC_VERSION
    created_at: datetime = Field(default_factory=_now)


def mean_applicable_score(dimensions: list[DimensionEvaluation]) -> float | None:
    scores = [
        dimension.score
        for dimension in dimensions
        if dimension.applicable and dimension.score is not None
    ]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _mean_applicable_confidence(dimensions: list[DimensionEvaluation]) -> float | None:
    confidences = [dimension.confidence for dimension in dimensions if dimension.applicable]
    if not confidences:
        return None
    return sum(confidences) / len(confidences)


def derive_advisory_status(
    *,
    status: PedagogicalEvalStatus,
    dimensions: list[DimensionEvaluation],
    overall_score: float | None,
) -> AdvisoryStatus:
    if status is PedagogicalEvalStatus.SKIPPED:
        return AdvisoryStatus.SKIPPED
    if status is PedagogicalEvalStatus.ERROR:
        return AdvisoryStatus.ERROR

    mean_confidence = _mean_applicable_confidence(dimensions)
    if mean_confidence is not None and mean_confidence < 0.5:
        return AdvisoryStatus.UNCERTAIN

    if overall_score is None:
        return AdvisoryStatus.WEAK
    if overall_score >= 4:
        return AdvisoryStatus.STRONG
    if overall_score >= 3:
        return AdvisoryStatus.ADEQUATE
    return AdvisoryStatus.WEAK


def skipped_evaluation(
    *,
    question_id: int | None,
    reason: str = "deterministic_failed",
) -> PedagogicalEvaluation:
    return PedagogicalEvaluation(
        question_id=question_id,
        status=PedagogicalEvalStatus.SKIPPED,
        skip_reason=reason,
        overall_advisory_score=None,
        overall_advisory_status=AdvisoryStatus.SKIPPED,
    )


def error_evaluation(
    *,
    question_id: int | None,
    detail: str,
    judge_model: str | None,
) -> PedagogicalEvaluation:
    return PedagogicalEvaluation(
        question_id=question_id,
        status=PedagogicalEvalStatus.ERROR,
        error_detail=detail,
        overall_advisory_score=None,
        overall_advisory_status=AdvisoryStatus.ERROR,
        judge_model=judge_model,
    )


def evaluation_from_judge_response(
    response: JudgeModelResponse,
    *,
    question_id: int | None,
    judge_model: str,
) -> PedagogicalEvaluation:
    overall_score = mean_applicable_score(response.dimensions)
    return PedagogicalEvaluation(
        question_id=question_id,
        status=PedagogicalEvalStatus.COMPLETED,
        overall_advisory_score=overall_score,
        overall_advisory_status=derive_advisory_status(
            status=PedagogicalEvalStatus.COMPLETED,
            dimensions=response.dimensions,
            overall_score=overall_score,
        ),
        dimensions=response.dimensions,
        judge_model=judge_model,
        rubric_version=RUBRIC_VERSION,
    )
