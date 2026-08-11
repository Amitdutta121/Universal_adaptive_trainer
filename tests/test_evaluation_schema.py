"""Pedagogical evaluation schema and advisory summary helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.evaluation.rubric import RUBRIC_VERSION, JudgeDimensionId
from app.evaluation.schema import (
    AdvisoryStatus,
    DimensionEvaluation,
    JudgeModelResponse,
    PedagogicalEvalStatus,
    derive_advisory_status,
    error_evaluation,
    evaluation_from_judge_response,
    mean_applicable_score,
    skipped_evaluation,
)


def _dim(
    dimension: JudgeDimensionId,
    *,
    score: int | None,
    applicable: bool = True,
    confidence: float = 0.9,
) -> DimensionEvaluation:
    return DimensionEvaluation(
        dimension=dimension,
        score=score,
        applicable=applicable,
        confidence=confidence,
        rationale="ok",
        issues=[],
    )


def test_rubric_version_locked() -> None:
    assert RUBRIC_VERSION == "pedagogical-judge@1"


def test_dimension_score_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        DimensionEvaluation(
            dimension=JudgeDimensionId.CLARITY,
            score=6,
            applicable=True,
            confidence=0.5,
            rationale="too high",
        )


@pytest.mark.parametrize(
    ("score", "applicable"),
    [
        (None, True),
        (3, False),
    ],
)
def test_dimension_score_must_match_applicability(
    score: int | None,
    applicable: bool,
) -> None:
    with pytest.raises(ValidationError):
        DimensionEvaluation(
            dimension=JudgeDimensionId.CLARITY,
            score=score,
            applicable=applicable,
            confidence=0.5,
            rationale="inconsistent",
        )


def test_mean_ignores_non_applicable() -> None:
    dims = [
        _dim(JudgeDimensionId.CLARITY, score=5),
        _dim(JudgeDimensionId.DISTRACTOR_QUALITY, score=None, applicable=False),
        _dim(JudgeDimensionId.SOURCE_GROUNDING, score=3),
    ]
    assert mean_applicable_score(dims) == 4.0


def test_advisory_status_bands_and_uncertain() -> None:
    strong = [_dim(JudgeDimensionId.CLARITY, score=5, confidence=0.9)]
    assert (
        derive_advisory_status(
            status=PedagogicalEvalStatus.COMPLETED,
            dimensions=strong,
            overall_score=5.0,
        )
        is AdvisoryStatus.STRONG
    )

    uncertain = [_dim(JudgeDimensionId.CLARITY, score=5, confidence=0.2)]
    assert (
        derive_advisory_status(
            status=PedagogicalEvalStatus.COMPLETED,
            dimensions=uncertain,
            overall_score=5.0,
        )
        is AdvisoryStatus.UNCERTAIN
    )

    assert (
        derive_advisory_status(
            status=PedagogicalEvalStatus.SKIPPED,
            dimensions=[],
            overall_score=None,
        )
        is AdvisoryStatus.SKIPPED
    )

    assert (
        derive_advisory_status(
            status=PedagogicalEvalStatus.COMPLETED,
            dimensions=[_dim(JudgeDimensionId.DISTRACTOR_QUALITY, score=None, applicable=False)],
            overall_score=None,
        )
        is AdvisoryStatus.UNCERTAIN
    )


def test_skipped_and_error_constructors() -> None:
    skipped = skipped_evaluation(question_id=3)
    assert skipped.status is PedagogicalEvalStatus.SKIPPED
    assert skipped.skip_reason == "deterministic_failed"
    assert skipped.overall_advisory_score is None
    assert skipped.rubric_version == RUBRIC_VERSION

    err = error_evaluation(question_id=3, detail="boom", judge_model="fake/m")
    assert err.status is PedagogicalEvalStatus.ERROR
    assert err.error_detail == "boom"


def test_evaluation_from_judge_response_sets_mean() -> None:
    response = JudgeModelResponse(
        dimensions=[
            _dim(JudgeDimensionId.CLARITY, score=4),
            _dim(JudgeDimensionId.SOURCE_GROUNDING, score=2),
        ]
    )
    evaluation = evaluation_from_judge_response(response, question_id=9, judge_model="openrouter/x")
    assert evaluation.status is PedagogicalEvalStatus.COMPLETED
    assert evaluation.overall_advisory_score == 3.0
    assert evaluation.overall_advisory_status is AdvisoryStatus.ADEQUATE
