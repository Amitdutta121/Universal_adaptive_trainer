"""The Jobs panel: every long-running professor action of the course, in one list.

Three tables hold jobs: ``background_jobs`` (bulk generation, coverage fills, book imports),
``generation_rounds`` (question rounds of a setup) and ``judge_batch_runs`` (judge
re-runs). They keep their own shapes; this route maps each onto :class:`JobOut` so the
header button, popover and run-detail window read one list.

A job is addressed as ``job-<n>``, ``round-<n>`` or ``judge-<run id>``. Cancelling asks a
running job to stop after the question in flight (:mod:`app.jobs.cancel`); retrying starts
a *new* job for what the old one did not finish. Which of the two a job allows, and what
its retry would do, is decided here and sent as ``can_cancel`` / ``retry_label``, so the
client never restates the rules.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select, update

from app.domain.enums import JobKind, JudgeBatchStatus, RoundStatus
from app.errors import DomainRuleError, NotFoundError
from app.generation.rounds import next_round, run_round
from app.jobs.cancel import CANCELLED
from app.jobs.queue import JobQueueDep
from app.persistence.models import (
    BackgroundJobRow,
    CurriculumVersionRow,
    GenerationRoundRow,
    JudgeBatchRunRow,
    QuestionSetupRow,
)
from app.persistence.repositories import JudgeBatchRunRepository
from app.web.routes.api.coverage import (
    GenerationClientDep,
    coverage_retry_targets,
    queue_coverage_fill,
)
from app.web.routes.api.deps import SPENDS_LLM_CREDIT, CourseScope, DbSession, ensure_in_course
from app.web.routes.api.evaluation import submit_judge_run
from app.web.routes.api.questions import retry_bulk_generation
from app.web.routes.api.schemas import JobListResponse, JobOut, JobStartedResponse

router = APIRouter(tags=["jobs"])

#: Per source table. The panel shows what is running and the recent past, not an archive.
RECENT_LIMIT = 30

_JUDGE_STATUS = {
    JudgeBatchStatus.SUBMITTED: "running",
    JudgeBatchStatus.IN_PROGRESS: "running",
    JudgeBatchStatus.COMPLETED: "done",
    JudgeBatchStatus.FAILED: "failed",
    JudgeBatchStatus.EXPIRED: "failed",
}

_IN_FLIGHT = (RoundStatus.QUEUED, RoundStatus.RUNNING)


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(session: DbSession, course: CourseScope) -> JobListResponse:
    """Recent and running jobs of the request's course, newest first."""
    jobs = [
        *(_from_background(row) for row in _background_rows(session, course)),
        *(_from_round(row, label) for row, label in _round_rows(session, course)),
        *(_from_judge_run(row) for row in _judge_rows(session, course)),
    ]
    jobs.sort(key=lambda job: job.created_at, reverse=True)
    return JobListResponse(jobs=jobs)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(session: DbSession, course: CourseScope, job_id: str) -> JobOut:
    """Stop a queued or running job. A queued one ends now; a running one after its question.

    Judge runs cannot be stopped: the provider runs a submitted batch to the end.
    """
    kind, key = _parse(job_id)
    if kind == "judge":
        _judge_run(session, key, course)
        raise DomainRuleError(
            "A judge run can't be stopped once it is submitted.",
            detail="The provider finishes the batch; its results still arrive in Jobs.",
        )
    if kind == "job":
        row = _background_job(session, key, course)
    else:
        row, _ = _round(session, key, course)
    if RoundStatus(row.status) not in _IN_FLIGHT:
        raise DomainRuleError("This job has already finished.", detail="There is nothing to stop.")
    if _is_running_import(row):
        raise DomainRuleError(
            "A book import can't be stopped once it has started.",
            detail="It is one step; delete the book afterwards if it is not wanted.",
        )
    now = datetime.now(UTC)
    model = type(row)
    # A queued job has not started: end it now. The update only matches while it is still
    # queued, so a runner that claimed it a moment ago is asked to stop instead.
    ended = session.execute(
        update(model)
        .where(model.id == row.id, model.status == RoundStatus.QUEUED)
        .values(
            status=RoundStatus.FAILED,
            error=CANCELLED,
            finished_at=now,
            cancel_requested_at=now,
        )
    )
    if ended.rowcount == 0:
        session.execute(update(model).where(model.id == row.id).values(cancel_requested_at=now))
    session.commit()
    session.refresh(row)
    if kind == "job":
        return _from_background(row)
    return _from_round(*_round(session, key, course))


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobStartedResponse,
    status_code=202,
    dependencies=SPENDS_LLM_CREDIT,
)
def retry_job(
    session: DbSession,
    course: CourseScope,
    job_id: str,
    queue: JobQueueDep,
    client: GenerationClientDep,
) -> JobStartedResponse:
    """Start a new job for what this one did not finish (see ``retry_label``).

    Takes no embedder: building one makes a provider client, which a bulk or judge retry
    never needs. A coverage retry's job builds the default one when it runs.
    """
    kind, key = _parse(job_id)
    if kind == "judge":
        run = _judge_run(session, key, course)
        if _JUDGE_STATUS[JudgeBatchStatus(run.status)] != "failed":
            raise DomainRuleError("Only a failed judge run can be retried.")
        started = submit_judge_run(session, course)
        return JobStartedResponse(job_id=f"judge-{started.run.run_id}")
    if kind == "round":
        row, _ = _round(session, key, course)
        if RoundStatus(row.status) is not RoundStatus.FAILED:
            raise DomainRuleError("Only a failed or cancelled round can be retried.")
        # The same size as the round being retried: a retry should not quietly grow.
        new = next_round(session, row.setup_id, size=max(row.requested, 1))
        if new.requested == 0:
            session.rollback()
            raise DomainRuleError(
                "Every cell has reached its target.",
                detail="Review the pending questions first; rejected ones free their cell.",
            )
        session.commit()
        queue.submit(run_round, new.id, client=client)
        return JobStartedResponse(job_id=f"round-{new.id}")

    job = _background_job(session, key, course)
    if _retry_label(job) is None:
        raise DomainRuleError("This job has nothing left to retry.")
    if JobKind(job.kind) is JobKind.BULK_GENERATION:
        started = retry_bulk_generation(session, course, job, queue)
    else:
        started = queue_coverage_fill(
            session,
            course,
            coverage_retry_targets(job),
            embedder=None,
            client=client,
            queue=queue,
            retry=True,
        )
    # A job is retried once: a second retry would make the same questions again.
    job.request = {**(job.request or {}), "retried_by": started.job_id}
    session.commit()
    return started


# --- addressing --------------------------------------------------------------


def _parse(job_id: str) -> tuple[str, str]:
    kind, _, key = job_id.partition("-")
    if kind not in {"job", "round", "judge"} or not key:
        raise NotFoundError(f"Job {job_id!r} does not exist.")
    if kind != "judge" and not key.isdigit():
        raise NotFoundError(f"Job {job_id!r} does not exist.")
    return kind, key


def _background_job(session: DbSession, key: str, course: int | None) -> BackgroundJobRow:
    row = session.get(BackgroundJobRow, int(key))
    if row is None:
        raise NotFoundError(f"Job job-{key} does not exist.")
    ensure_in_course(row.course_id, course, f"Job job-{key}")
    return row


def _round(session: DbSession, key: str, course: int | None) -> tuple[GenerationRoundRow, str]:
    found = session.execute(
        select(GenerationRoundRow, CurriculumVersionRow)
        .join(QuestionSetupRow, QuestionSetupRow.id == GenerationRoundRow.setup_id)
        .join(
            CurriculumVersionRow,
            CurriculumVersionRow.id == QuestionSetupRow.curriculum_version_id,
        )
        .where(GenerationRoundRow.id == int(key))
    ).first()
    if found is None:
        raise NotFoundError(f"Job round-{key} does not exist.")
    row, version = found
    ensure_in_course(version.course_id, course, f"Job round-{key}")
    return row, version.label


def _judge_run(session: DbSession, run_id: str, course: int | None) -> JudgeBatchRunRow:
    run = JudgeBatchRunRepository(session).get(run_id)
    ensure_in_course(run.course_id, course, f"Job judge-{run_id}")
    return run


# --- listing -----------------------------------------------------------------


def _background_rows(session: DbSession, course: int | None) -> list[BackgroundJobRow]:
    stmt = select(BackgroundJobRow).order_by(BackgroundJobRow.id.desc()).limit(RECENT_LIMIT)
    if course is not None:
        stmt = stmt.where(BackgroundJobRow.course_id == course)
    return list(session.scalars(stmt))


def _round_rows(session: DbSession, course: int | None) -> list[tuple[GenerationRoundRow, str]]:
    stmt = (
        select(GenerationRoundRow, CurriculumVersionRow.label)
        .join(QuestionSetupRow, QuestionSetupRow.id == GenerationRoundRow.setup_id)
        .join(
            CurriculumVersionRow,
            CurriculumVersionRow.id == QuestionSetupRow.curriculum_version_id,
        )
        .order_by(GenerationRoundRow.id.desc())
        .limit(RECENT_LIMIT)
    )
    if course is not None:
        stmt = stmt.where(CurriculumVersionRow.course_id == course)
    return [(row, label) for row, label in session.execute(stmt)]


def _judge_rows(session: DbSession, course: int | None) -> list[JudgeBatchRunRow]:
    stmt = select(JudgeBatchRunRow).order_by(JudgeBatchRunRow.id.desc()).limit(RECENT_LIMIT)
    if course is not None:
        stmt = stmt.where(JudgeBatchRunRow.course_id == course)
    return list(session.scalars(stmt))


def _status(row: BackgroundJobRow | GenerationRoundRow) -> str:
    """``cancelled`` is a failure the professor asked for; the tables store it as failed."""
    status = RoundStatus(row.status)
    if status is RoundStatus.FAILED and row.cancel_requested_at is not None:
        return "cancelled"
    return status.value


def _is_running_import(row: BackgroundJobRow | GenerationRoundRow) -> bool:
    return (
        isinstance(row, BackgroundJobRow)
        and JobKind(row.kind) is JobKind.BOOK_IMPORT
        and RoundStatus(row.status) is RoundStatus.RUNNING
    )


def _can_cancel(row: BackgroundJobRow | GenerationRoundRow) -> bool:
    return (
        RoundStatus(row.status) in _IN_FLIGHT
        and row.cancel_requested_at is None
        and not _is_running_import(row)
    )


def _retry_label(row: BackgroundJobRow) -> str | None:
    """What retrying this background job would do, or ``None`` when it would do nothing."""
    status = RoundStatus(row.status)
    if status in _IN_FLIGHT or (row.request or {}).get("retried_by"):
        return None
    if JobKind(row.kind) is JobKind.BOOK_IMPORT:
        # A refused document is refused again; importing it anew is a new upload.
        return None
    if JobKind(row.kind) is JobKind.BULK_GENERATION:
        remaining = row.total - row.done
        return (
            f"Retry the remaining {remaining}"
            if status is RoundStatus.FAILED and remaining
            else None
        )
    gaps = len(coverage_retry_targets(row))
    if not gaps:
        return None
    plural = "s" if gaps != 1 else ""
    if status is RoundStatus.DONE:
        return f"Retry {gaps} failed gap{plural}"
    return f"Retry the remaining {gaps} gap{plural}"


def _link(row: BackgroundJobRow) -> str | None:
    """The course page holding the job's output: its questions, or the imported book."""
    if JobKind(row.kind) is JobKind.BOOK_IMPORT:
        book = (row.result or {}).get("book")
        return f"/books/{book['id']}" if book else None
    return f"/questions?run_id={row.run_id}" if row.run_id else None


def _from_background(row: BackgroundJobRow) -> JobOut:
    return JobOut(
        id=f"job-{row.id}",
        kind=JobKind(row.kind).value,
        title=row.title,
        status=_status(row),
        done=row.done,
        total=row.total,
        error=row.error,
        link=_link(row),
        result=row.result,
        can_cancel=_can_cancel(row),
        cancel_requested=row.cancel_requested_at is not None,
        retry_label=_retry_label(row),
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _from_round(row: GenerationRoundRow, taxonomy_label: str) -> JobOut:
    return JobOut(
        id=f"round-{row.id}",
        kind="question_round",
        title=f"Question round {row.number} · {taxonomy_label}",
        status=_status(row),
        done=row.produced + row.dropped + row.skipped,
        total=row.requested,
        counts={"made": row.produced, "dropped": row.dropped, "skipped": row.skipped},
        error=row.error,
        link=f"/review?round={row.id}",
        can_cancel=_can_cancel(row),
        cancel_requested=row.cancel_requested_at is not None,
        retry_label="Start the next round"
        if RoundStatus(row.status) is RoundStatus.FAILED
        else None,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _from_judge_run(row: JudgeBatchRunRow) -> JobOut:
    status = _JUDGE_STATUS[JudgeBatchStatus(row.status)]
    return JobOut(
        id=f"judge-{row.run_id}",
        kind="judge_run",
        title=f"Judge run · {row.question_count} questions",
        status=status,
        done=row.completed_count + row.failed_count,
        total=row.question_count,
        counts={"judged": row.completed_count, "failed": row.failed_count},
        error=row.error_detail,
        link="/judges",
        retry_label="Run judges again" if status == "failed" else None,
        created_at=row.created_at,
        started_at=row.submitted_at,
        finished_at=row.completed_at,
    )
