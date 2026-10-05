"""Evaluation endpoints: bulk judge re-runs, and the history they build up.

A re-run is asynchronous (ADR-030): submitting one returns immediately with a
run id, and results are collected by calling the poll endpoint. There is no
scheduler in this repository and these endpoints do not add one -- polling is
something the professor (or a client) does, which is why it is a route rather
than a background task.

The history endpoint is read-only and always available, including for questions
whose evaluations all predate batch re-runs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.evaluation import poll_and_ingest, submit_bank_rerun
from app.persistence.models import JudgeBatchRunRow
from app.persistence.repositories import (
    JudgeBatchRunRepository,
    QuestionEvaluationRepository,
)
from app.web.routes.api.deps import CourseScope, DbSession, ensure_in_course, question_in_course
from app.web.routes.api.schemas import (
    BatchRunListResponse,
    EvaluationHistoryEntry,
    EvaluationHistoryResponse,
    JudgeBatchRunOut,
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


@router.post(
    "/evaluation/batch-runs",
    response_model=SubmitBatchRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
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
    try:
        result = submit_bank_rerun(session, question_ids=request.question_ids, course_id=course)
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


@router.post("/evaluation/batch-runs/{run_id}/poll", response_model=PollBatchRunResponse)
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
