"""Advisory pedagogical evaluation boundary.

Responsibility
    Structured LLM rubric output, stored evaluation records, and summary helpers
    for an advisory pedagogical judge. The judge supplements deterministic
    validation; it never overrides a failed deterministic check.

Status
    Schema, rubric constants, summary helpers, and the advisory judge service
    are implemented.

Key rules
    * Overall advisory score is an unweighted arithmetic mean of applicable
      dimension scores, provided as a summary only.
    * Individual dimension results remain the primary evaluation output.
    * Evaluation does not set :class:`~app.domain.enums.QuestionStatus`.

Allowed dependencies
    ``app.domain``, ``app.llm``, ``app.ingestion`` retrieval, ``app.persistence``
    curriculum repositories, ``app.config`` via existing patterns.
    Must not import ``app.adaptive`` or ``app.personalization``.
"""

from __future__ import annotations

from app.evaluation.rubric import RUBRIC_VERSION, JudgeDimensionId
from app.evaluation.schema import (
    AdvisoryStatus,
    DimensionEvaluation,
    JudgeModelResponse,
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
    derive_advisory_status,
    error_evaluation,
    evaluation_from_judge_response,
    mean_applicable_score,
    skipped_evaluation,
)
from app.evaluation.service import JUDGE_MAX_ATTEMPTS, PedagogicalJudge

__all__ = [
    "JUDGE_MAX_ATTEMPTS",
    "RUBRIC_VERSION",
    "AdvisoryStatus",
    "DimensionEvaluation",
    "JudgeDimensionId",
    "JudgeModelResponse",
    "PedagogicalEvalStatus",
    "PedagogicalEvaluation",
    "PedagogicalJudge",
    "derive_advisory_status",
    "error_evaluation",
    "evaluation_from_judge_response",
    "mean_applicable_score",
    "skipped_evaluation",
]
