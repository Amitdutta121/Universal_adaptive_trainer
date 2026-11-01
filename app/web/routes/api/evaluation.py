"""Evaluation endpoints: bulk judge re-runs, and the history they build up.

A re-run is asynchronous (ADR-030): submitting one returns immediately with a
run id. Results are collected by :mod:`app.jobs.judge_collector`, which polls
every unfinished run on a timer (including after a restart); the poll endpoint
still collects one run on demand. The Studio starts a run from the Judges page
("Run judges") and follows it in the Jobs panel.

The history endpoint is read-only and always available, including for questions
whose evaluations all predate batch re-runs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status
from sqlalchemy import select

from app.config import get_settings
from app.domain.enums import JudgeBatchStatus
from app.errors import DomainRuleError
from app.evaluation import poll_and_ingest, submit_bank_rerun
from app.evaluation.batch_service import judgeable_questions
from app.persistence.models import JudgeBatchRunRow
from app.persistence.repositories import (
    JudgeBatchRunRepository,
    QuestionEvaluationRepository,
)
from app.web.routes.api.deps import (
    SPENDS_LLM_CREDIT,
    CourseScope,
    DbSession,
    ensure_in_course,
    question_in_course,
)
from app.web.routes.api.schemas import (
    BatchRunListResponse,
    EvaluationHistoryEntry,
    EvaluationHistoryResponse,
    JudgeBatchRunOut,
    JudgeRerunPreviewOut,
    PollBatchRunResponse,
    SubmitBatchRunRequest,
    SubmitBatchRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evaluation"])


def _run_in_course(session: DbSession, run_id: str, course: int | None) -> JudgeBatchRunRow:
    run = JudgeBatchRunRepository(session).get(run_id)
    ensure_in_course(run.course_id, course, f"Batch run {run_id}")
    return run


def _active_run_id(session: DbSession, course: int | None) -> str | None:
    """A run of this course the provider is still working on, if any."""
    stmt = select(JudgeBatchRunRow.run_id).where(
        JudgeBatchRunRow.status.in_([JudgeBatchStatus.SUBMITTED, JudgeBatchStatus.IN_PROGRESS])
    )
    if course is not None:
        stmt = stmt.where(JudgeBatchRunRow.course_id == course)
    return session.scalars(stmt.limit(1)).first()


@router.get("/evaluation/rerun-preview", response_model=JudgeRerunPreviewOut)
def rerun_preview(session: DbSession, course: CourseScope) -> JudgeRerunPreviewOut:
    """What "Run judges" would do now: how many questions, or why it can't run."""
    settings = get_settings()
    reason = None
    if not settings.judge_batch_enabled:
        reason = "Judge re-runs are switched off. Set JUDGE_BATCH_ENABLED=true to enable them."
    elif settings.judge_batch_credential is None:
        reason = "Judge re-runs need an API key. Set JUDGE_BATCH_API_KEY or LLM_API_KEY."
    return JudgeRerunPreviewOut(
        enabled=reason is None,
        disabled_reason=reason,
        eligible=len(judgeable_questions(session, course)),
        active_run_id=_active_run_id(session, course),
    )


@router.post(
    "/evaluation/batch-runs",
    response_model=SubmitBatchRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=SPENDS_LLM_CREDIT,
)
def submit_batch_run(
    session: DbSession, course: CourseScope, payload: SubmitBatchRunRequest | None = None
) -> SubmitBatchRunResponse:
    """Submit the eligible question bank for re-judging.

    202 rather than 201: the run is accepted, not finished. Nothing has been
    evaluated when this returns, and results appear only after a poll.
    """
    request = payload or SubmitBatchRunRequest()
    # Named questions of another course are a 404, not silently dropped (ADR-060).
    for question_id in request.question_ids or []:
        question_in_course(session, question_id, course)
    return submit_judge_run(session, course, question_ids=request.question_ids)


def submit_judge_run(
    session: DbSession, course: int | None, *, question_ids: list[int] | None = None
) -> SubmitBatchRunResponse:
    """Submit a re-run unless one of this course is still being judged."""
    if _active_run_id(session, course) is not None:
        raise DomainRuleError(
            "A judge run is already in progress for this course.",
            detail="Its results are collected automatically; follow it in Jobs.",
        )
    try:
        result = submit_bank_rerun(session, question_ids=question_ids, course_id=course)
    except Exception:
        session.rollback()
        raise
    return SubmitBatchRunResponse.from_result(result)


@router.get("/evaluation/batch-runs", response_model=BatchRunListResponse)
def list_batch_runs(
    session: DbSession, course: CourseScope, limit: int = 20
) -> BatchRunListResponse:
    """The course's recent re-runs, newest first."""
    runs = JudgeBatchRunRepository(session).list_recent(limit=limit, course_id=course)
    return BatchRunListResponse(
        runs=[JudgeBatchRunOut.from_row(row) for row in runs], total=len(runs)
    )


@router.get("/evaluation/batch-runs/{run_id}", response_model=JudgeBatchRunOut)
def get_batch_run(session: DbSession, course: CourseScope, run_id: str) -> JudgeBatchRunOut:
    """One re-run's stored status, without contacting the provider."""
    return JudgeBatchRunOut.from_row(_run_in_course(session, run_id, course))


@router.post(
    "/evaluation/batch-runs/{run_id}/poll",
    response_model=PollBatchRunResponse,
    dependencies=SPENDS_LLM_CREDIT,
)
def poll_batch_run(session: DbSession, course: CourseScope, run_id: str) -> PollBatchRunResponse:
    """Ask the provider about a run and record whatever has finished.

    Idempotent. Polling a run whose results are already recorded reports them as
    ``already_recorded`` and writes nothing.
    """
    _run_in_course(session, run_id, course)
    try:
        result = poll_and_ingest(session, run_id)
    except Exception:
        session.rollback()
        raise
    return PollBatchRunResponse.from_result(result)


@router.get(
    "/questions/{question_id}/evaluations",
    response_model=EvaluationHistoryResponse,
)
def question_evaluations(
    session: DbSession, course: CourseScope, question_id: int
) -> EvaluationHistoryResponse:
    """Every evaluation this question has received, newest first.

    The newest row is flagged ``is_current`` because it is what
    ``questions.pedagogical_eval_json`` holds; the older rows are what the judge
    said before, retained rather than overwritten.
    """
    # Raises NotFoundError for an unknown question, so history and detail agree
    # about which questions exist.
    question_in_course(session, question_id, course)
    rows = QuestionEvaluationRepository(session).list_for_question(question_id)
    return EvaluationHistoryResponse(
        question_id=question_id,
        evaluations=[
            EvaluationHistoryEntry.from_row(row, is_current=index == 0)
            for index, row in enumerate(rows)
        ],
        total=len(rows),
    )
