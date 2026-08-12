"""Bulk judge re-runs and the evaluation history behind them (ADR-030).

What this adds
    The judge used to run in exactly one place -- once per question, during
    generation -- and its answer was written to ``questions.pedagogical_eval_json``.
    Re-judging anything meant overwriting what the judge said the first time.
    This module re-runs the judge over the whole bank as an asynchronous
    provider batch, and records every evaluation it ever produces.

What stays true
    ``questions.pedagogical_eval_json`` is still the *current* evaluation and is
    still what every existing reader uses. This module adds history beside it;
    it does not move the value those readers depend on.

    A question that failed or skipped deterministic validation is not re-judged,
    because the judge never ran on those in the first place (ADR-024). Bulk
    re-running must not quietly extend the judge's reach.

Collection is manual
    There is no scheduler in this repository and this does not add one. A
    submitted run sits until someone asks for its results, which is why
    :func:`poll_and_ingest` is safe to call at any time and any number of times.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.enums import EvaluationTrigger, JudgeBatchStatus
from app.domain.questions import Question
from app.errors import AdaptiveTrainerError, ConfigurationError, DomainRuleError
from app.evaluation.rubric import RUBRIC_VERSION
from app.evaluation.schema import (
    JudgeModelResponse,
    PedagogicalEvaluation,
    error_evaluation,
    evaluation_from_judge_response,
    humanize_judge_error_detail,
)
from app.evaluation.service import build_judge_prompts
from app.llm import batch as batch_transport
from app.llm.batch import BatchRequestItem, BatchResultLine
from app.persistence.models import JudgeBatchRunRow, QuestionEvaluationRow, QuestionRow
from app.persistence.repositories import (
    JudgeBatchRunRepository,
    QuestionEvaluationRepository,
    QuestionRepository,
)

logger = logging.getLogger(__name__)

#: Evaluation statuses that carry an actual judgement. Only these may become the
#: current evaluation, so a failed re-run cannot erase a completed one.
INFORMATIVE_STATUSES = frozenset({"completed"})

#: Provider statuses that end a run, mapped onto our own vocabulary. A run the
#: provider cancelled is recorded as failed, with the cancellation named in
#: ``error_detail`` -- there is no separate cancelled state to show a professor.
TERMINAL_PROVIDER_STATUSES: dict[str, JudgeBatchStatus] = {
    "completed": JudgeBatchStatus.COMPLETED,
    "failed": JudgeBatchStatus.FAILED,
    "expired": JudgeBatchStatus.EXPIRED,
    "cancelled": JudgeBatchStatus.FAILED,
    "canceled": JudgeBatchStatus.FAILED,
}


def _now() -> datetime:
    return datetime.now(UTC)


def new_run_id() -> str:
    return uuid.uuid4().hex


def record_evaluation(
    session: Session,
    question_id: int,
    evaluation: PedagogicalEvaluation,
    *,
    run_id: str,
    trigger: EvaluationTrigger,
) -> QuestionEvaluationRow:
    """Append one evaluation to a question's history, and usually make it current.

    History is always appended: every evaluation is retained, including the
    failures, because "the judge could not answer on this date" is part of the
    record.

    **A failed evaluation does not displace a completed one.** If the incoming
    evaluation is an ``error`` or ``skipped`` and the question already carries a
    ``completed`` one, the current value is left alone. ADR-024 already says an
    ``error`` evaluation cannot fail a question that passed deterministic checks;
    the same reasoning applies here, because a re-run that could not reach the
    model says nothing about the question and must not replace a real judgement
    with a blank one. The failure is still in history, and the next successful
    re-run still takes over.

    Does not commit -- the caller decides the transaction boundary, because
    generation writes several questions per commit while ingest commits per
    result.
    """
    payload = evaluation.model_dump(mode="json")
    row = QuestionEvaluationRepository(session).add(
        QuestionEvaluationRow(
            question_id=question_id,
            evaluation=payload,
            judge_model=evaluation.judge_model,
            rubric_version=evaluation.rubric_version,
            eval_status=evaluation.status.value,
            advisory_status=evaluation.overall_advisory_status.value,
            run_id=run_id,
            trigger=trigger,
            created_at=evaluation.created_at,
        )
    )
    question = session.get(QuestionRow, question_id)
    if question is not None and _may_become_current(question.pedagogical_eval, evaluation):
        question.pedagogical_eval = payload
    return row


def _may_become_current(existing: dict | None, incoming: PedagogicalEvaluation) -> bool:
    """Whether ``incoming`` should replace ``existing`` as the current evaluation."""
    if incoming.status.value in INFORMATIVE_STATUSES:
        return True
    if not isinstance(existing, dict):
        return True
    return existing.get("status") not in INFORMATIVE_STATUSES


def backfill_generation_history(session: Session) -> int:
    """Give every pre-existing evaluation a history row. Returns rows written.

    Evaluations recorded before this table existed are real judge output and
    must not be lost the moment a re-run overwrites the column holding them.
    Each is filed under ``generation``, with its **stored** ``created_at``
    preserved rather than today's date, so history stays ordered by when the
    judge actually spoke.

    Idempotent: the second call finds nothing to write, because the set it works
    from is defined as evaluations with no history row.
    """
    pending = QuestionRepository(session).list_evaluated_without_history()
    if not pending:
        return 0

    run_id = f"backfill-{new_run_id()}"
    repository = QuestionEvaluationRepository(session)
    written = 0
    for question in pending:
        payload = question.pedagogical_eval
        if not isinstance(payload, dict):  # pragma: no cover - column guarantees dict | None
            continue
        created_at, status, advisory = _describe_stored_evaluation(payload)
        repository.add(
            QuestionEvaluationRow(
                question_id=question.id,
                evaluation=payload,
                judge_model=_optional_str(payload.get("judge_model")),
                rubric_version=_optional_str(payload.get("rubric_version")),
                eval_status=status,
                advisory_status=advisory,
                run_id=run_id,
                trigger=EvaluationTrigger.GENERATION,
                created_at=created_at or question.created_at,
            )
        )
        written += 1
    logger.info("Backfilled %d pre-existing evaluations into history", written)
    return written


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _describe_stored_evaluation(payload: dict) -> tuple[datetime | None, str | None, str | None]:
    """Read the denormalised columns out of a stored evaluation blob.

    Read defensively rather than through :class:`PedagogicalEvaluation`: a blob
    written by an older rubric may no longer validate, and that is a reason to
    keep it verbatim in history, not a reason to drop it (same policy ADR-029
    applies to calibration).
    """
    created_at: datetime | None = None
    raw_created = payload.get("created_at")
    if isinstance(raw_created, str):
        try:
            created_at = datetime.fromisoformat(raw_created)
        except ValueError:
            logger.warning("Backfilled evaluation has an unreadable created_at")
    return (
        created_at,
        _optional_str(payload.get("status")),
        _optional_str(payload.get("overall_advisory_status")),
    )


@dataclass(frozen=True)
class SubmissionResult:
    """What a submit call did, in the terms the API and page report."""

    run: JudgeBatchRunRow
    submitted: int
    skipped: int
    backfilled: int


def submit_bank_rerun(
    session: Session,
    *,
    settings: Settings | None = None,
    question_ids: list[int] | None = None,
) -> SubmissionResult:
    """Submit the eligible question bank for re-judging as a batch run.

    Eligibility is deterministic-validation-passed, per ADR-024. Questions whose
    prompts cannot be rebuilt (a deleted source section, a superseded curriculum)
    are skipped and counted rather than submitted with missing context.

    The backfill runs first, before anything can overwrite
    ``pedagogical_eval_json``, so no pre-existing evaluation is lost to this run.

    Raises:
        ConfigurationError: if batch re-runs are disabled or uncredentialed.
        DomainRuleError: if no question is eligible.
    """
    settings = settings or get_settings()
    if not settings.judge_batch_enabled:
        raise ConfigurationError(
            "Bulk judge re-run is disabled.",
            detail="Set JUDGE_BATCH_ENABLED=true in your .env file to enable it.",
        )
    if settings.judge_batch_credential is None:
        raise ConfigurationError(
            "The bulk judge re-run needs an API key.",
            detail="Set JUDGE_BATCH_API_KEY, or LLM_API_KEY, in your .env file.",
        )

    backfilled = backfill_generation_history(session)

    candidates = QuestionRepository(session).list_judgeable()
    if question_ids is not None:
        wanted = set(question_ids)
        candidates = [row for row in candidates if row.id in wanted]
    if not candidates:
        session.rollback()
        raise DomainRuleError(
            "No question is eligible for re-judging.",
            detail=(
                "The judge only scores questions that passed deterministic validation "
                "(ADR-024). Generate or validate questions first."
            ),
        )

    run_id = new_run_id()
    items, skipped = _build_request_items(session, candidates, run_id=run_id)
    if not items:
        session.rollback()
        raise DomainRuleError(
            "No eligible question could be prepared for re-judging.",
            detail=f"{skipped} question(s) could not have their source context rebuilt.",
        )

    schema = JudgeModelResponse.model_json_schema()
    batch_ids: list[str] = []
    for chunk in batch_transport.split_into_jobs(
        items, max_per_job=settings.judge_batch_max_requests_per_job
    ):
        batch_ids.append(
            batch_transport.submit_batch(chunk, response_schema=schema, settings=settings)
        )

    run = JudgeBatchRunRepository(session).add(
        JudgeBatchRunRow(
            run_id=run_id,
            provider_batch_ids=batch_ids,
            status=JudgeBatchStatus.SUBMITTED,
            model=settings.judge_batch_route,
            rubric_version=RUBRIC_VERSION,
            submitted_at=_now(),
            question_count=len(items),
        )
    )
    session.commit()
    logger.info(
        "Submitted judge re-run %s: %d questions across %d provider job(s)",
        run_id,
        len(items),
        len(batch_ids),
    )
    return SubmissionResult(run=run, submitted=len(items), skipped=skipped, backfilled=backfilled)


def _build_request_items(
    session: Session, questions: list[QuestionRow], *, run_id: str
) -> tuple[list[BatchRequestItem], int]:
    """Build one request per question, counting those whose context is gone."""
    items: list[BatchRequestItem] = []
    skipped = 0
    for row in questions:
        try:
            system, prompt = build_judge_prompts(session, Question.model_validate(row))
        except (AdaptiveTrainerError, LookupError, TypeError, ValueError) as exc:
            logger.warning("Skipping question %s in run %s: %s", row.id, run_id, exc)
            skipped += 1
            continue
        items.append(
            BatchRequestItem(
                custom_id=batch_transport.build_custom_id(run_id, row.id),
                system=system,
                prompt=prompt,
            )
        )
    return items, skipped


@dataclass(frozen=True)
class IngestResult:
    """What one poll did."""

    run: JudgeBatchRunRow
    status: JudgeBatchStatus
    ingested: int
    failed: int
    already_recorded: int


def poll_and_ingest(
    session: Session, run_id: str, *, settings: Settings | None = None
) -> IngestResult:
    """Ask the provider about a run and record whatever has finished.

    Safe to call repeatedly. Results already recorded under this run are counted
    and skipped, so a second poll of a completed run writes nothing -- which is
    what makes a manual "check for results" button usable without a professor
    having to remember whether they already pressed it.

    A result line that cannot be read becomes an ``error`` evaluation for that
    question, and the remaining lines are still ingested. One malformed answer
    must not cost the run every other answer in it.
    """
    settings = settings or get_settings()
    repository = JudgeBatchRunRepository(session)
    run = repository.get(run_id)
    if run.status.is_terminal() and run.status is not JudgeBatchStatus.COMPLETED:
        # A failed or expired run has nothing left to collect; re-polling it
        # would only re-ask the provider about a job it already gave up on.
        return IngestResult(run=run, status=run.status, ingested=0, failed=0, already_recorded=0)

    states = [
        batch_transport.fetch_status(batch_id, settings=settings)
        for batch_id in run.provider_batch_ids
    ]
    lines: list[BatchResultLine] = []
    for state in states:
        lines.extend(batch_transport.parse_results(state.raw_results))

    already = QuestionEvaluationRepository(session).question_ids_for_run(run_id)
    ingested = 0
    failed = 0
    already_recorded = 0
    for line in lines:
        outcome = _ingest_line(session, run_id, line, already=already, settings=settings)
        if outcome is None:
            already_recorded += 1
            continue
        if outcome:
            ingested += 1
        else:
            failed += 1
        session.commit()

    run.completed_count += ingested
    run.failed_count += failed
    run.status = _run_status(states)
    run.error_detail = _run_error_detail(states) or run.error_detail
    if run.status.is_terminal():
        run.completed_at = _now()
    session.commit()
    logger.info(
        "Polled judge re-run %s: status=%s ingested=%d failed=%d skipped=%d",
        run_id,
        run.status.value,
        ingested,
        failed,
        already_recorded,
    )
    return IngestResult(
        run=run,
        status=run.status,
        ingested=ingested,
        failed=failed,
        already_recorded=already_recorded,
    )


def _ingest_line(
    session: Session,
    run_id: str,
    line: BatchResultLine,
    *,
    already: set[int],
    settings: Settings,
) -> bool | None:
    """Record one result line. ``None`` means it was already recorded.

    Returns ``True`` when a completed evaluation was stored and ``False`` when
    an advisory error was stored in its place.
    """
    try:
        line_run_id, question_id = batch_transport.parse_custom_id(line.custom_id)
    except ValueError:
        logger.warning("Dropping batch result with unparseable custom_id %r", line.custom_id)
        return None
    if line_run_id != run_id:
        logger.warning("Dropping batch result %r that belongs to another run", line.custom_id)
        return None
    if question_id in already:
        return None
    if session.get(QuestionRow, question_id) is None:
        logger.warning("Dropping batch result for question %s, which no longer exists", question_id)
        return None

    already.add(question_id)
    evaluation, ok = _evaluation_from_line(line, question_id=question_id, settings=settings)
    record_evaluation(
        session,
        question_id,
        evaluation,
        run_id=run_id,
        trigger=EvaluationTrigger.BATCH_RERUN,
    )
    return ok


def _evaluation_from_line(
    line: BatchResultLine, *, question_id: int, settings: Settings
) -> tuple[PedagogicalEvaluation, bool]:
    """Turn one result line into an evaluation, never raising."""
    judge_model = f"{settings.judge_batch_route} (batch)"
    if line.content is None:
        return (
            error_evaluation(
                question_id=question_id,
                detail=humanize_judge_error_detail(line.error),
                judge_model=judge_model,
            ),
            False,
        )
    try:
        response = JudgeModelResponse.model_validate(json.loads(line.content))
    except (ValueError, ValidationError) as exc:
        return (
            error_evaluation(
                question_id=question_id,
                detail=humanize_judge_error_detail(f"{type(exc).__name__}: {exc}"),
                judge_model=judge_model,
            ),
            False,
        )
    return (
        evaluation_from_judge_response(response, question_id=question_id, judge_model=judge_model),
        True,
    )


def _run_status(states: list[batch_transport.BatchJobState]) -> JudgeBatchStatus:
    """Reduce every provider job's status to one status for the run.

    A run is only complete when all of its jobs are, and one failed or expired
    job fails the run: reporting "completed" while part of the bank was never
    judged would be a false statement about coverage.
    """
    if not states:
        return JudgeBatchStatus.FAILED
    mapped = [TERMINAL_PROVIDER_STATUSES.get(state.status.lower()) for state in states]
    if any(status is JudgeBatchStatus.EXPIRED for status in mapped):
        return JudgeBatchStatus.EXPIRED
    if any(status is JudgeBatchStatus.FAILED for status in mapped):
        return JudgeBatchStatus.FAILED
    if all(status is JudgeBatchStatus.COMPLETED for status in mapped):
        return JudgeBatchStatus.COMPLETED
    return JudgeBatchStatus.IN_PROGRESS


def _run_error_detail(states: list[batch_transport.BatchJobState]) -> str | None:
    details = [state.error_detail for state in states if state.error_detail]
    if not details:
        return None
    return " | ".join(details)[:1000]
