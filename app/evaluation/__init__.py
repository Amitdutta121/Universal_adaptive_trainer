"""Advisory pedagogical evaluation boundary.

Responsibility
    Structured LLM rubric output, stored evaluation records, and summary helpers
    for an advisory pedagogical judge. The judge supplements deterministic
    validation; it never overrides a failed deterministic check.

Status
    Schema, rubric constants, summary helpers, the advisory judge service, and
    bulk asynchronous re-runs with retained history are implemented.

Key rules
    * Overall advisory score is an unweighted arithmetic mean of applicable
      dimension scores, provided as a summary only.
    * Individual dimension results remain the primary evaluation output.
    * Evaluation does not set :class:`~app.domain.enums.QuestionStatus`.
    * Every evaluation is retained; ``questions.pedagogical_eval_json`` holds
      the current one and ``question_evaluations`` holds all of them (ADR-030).

Allowed dependencies
    ``app.domain``, ``app.llm``, ``app.ingestion`` retrieval, ``app.persistence``
    curriculum repositories, ``app.config`` via existing patterns.
    Must not import ``app.adaptive`` or ``app.personalization``.
"""

from __future__ import annotations

from app.evaluation.batch_service import (
    IngestResult,
    SubmissionResult,
    backfill_generation_history,
    new_run_id,
    poll_and_ingest,
    record_evaluation,
    submit_bank_rerun,
)
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
    humanize_judge_error_detail,
    mean_applicable_score,
    skipped_evaluation,
)
from app.evaluation.service import JUDGE_MAX_ATTEMPTS, PedagogicalJudge, build_judge_prompts

__all__ = [
    "JUDGE_MAX_ATTEMPTS",
    "RUBRIC_VERSION",
    "AdvisoryStatus",
    "DimensionEvaluation",
    "IngestResult",
    "JudgeDimensionId",
    "JudgeModelResponse",
    "PedagogicalEvalStatus",
    "PedagogicalEvaluation",
    "PedagogicalJudge",
    "SubmissionResult",
    "backfill_generation_history",
    "build_judge_prompts",
    "derive_advisory_status",
    "error_evaluation",
    "evaluation_from_judge_response",
    "humanize_judge_error_detail",
    "mean_applicable_score",
    "new_run_id",
    "poll_and_ingest",
    "record_evaluation",
    "skipped_evaluation",
    "submit_bank_rerun",
]
