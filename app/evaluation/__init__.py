"""Advisory pedagogical evaluation boundary.

Responsibility
    Four advisory judges per question -- issues, subtopic, difficulty and
    generatability -- their stored results, and the gate derived from them. The
    judges supplement deterministic validation; they never override a failed
    deterministic check.

Status
    Judge prompts, verdict schemas, the synchronous judge service, and bulk
    asynchronous re-runs with retained history are implemented.

Key rules
    * One model call per metric. A judge that fails is an absent measurement,
      not a failing verdict, and never stops a question reaching review.
    * ``passed`` is derived here by comparing a judge's answer with what the
      generator claimed; no judge reports its own pass or fail.
    * The gate is a count of passing metrics: all four approve, none reject,
      anything between needs review. It is ``None`` unless all four answered.
    * The gate is advisory. The professor's own review stays the authority.
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
from app.evaluation.prompts import JUDGE_ISSUE_CODES, RUBRIC_VERSION, JudgeContext
from app.evaluation.schema import (
    DifficultyVerdict,
    GeneratabilityVerdict,
    IssuesVerdict,
    MetricResult,
    MetricStatus,
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
    SubtopicVerdict,
    derive_gate,
    evaluation_from_metrics,
    failed_metric,
    humanize_judge_error_detail,
    skipped_evaluation,
)
from app.evaluation.service import (
    JUDGE_MAX_ATTEMPTS,
    PedagogicalJudge,
    build_judge_context,
    result_from_verdict,
)

__all__ = [
    "JUDGE_ISSUE_CODES",
    "JUDGE_MAX_ATTEMPTS",
    "RUBRIC_VERSION",
    "DifficultyVerdict",
    "GeneratabilityVerdict",
    "IngestResult",
    "IssuesVerdict",
    "JudgeContext",
    "MetricResult",
    "MetricStatus",
    "PedagogicalEvalStatus",
    "PedagogicalEvaluation",
    "PedagogicalJudge",
    "SubmissionResult",
    "SubtopicVerdict",
    "backfill_generation_history",
    "build_judge_context",
    "derive_gate",
    "evaluation_from_metrics",
    "failed_metric",
    "humanize_judge_error_detail",
    "new_run_id",
    "poll_and_ingest",
    "record_evaluation",
    "result_from_verdict",
    "skipped_evaluation",
    "submit_bank_rerun",
]
