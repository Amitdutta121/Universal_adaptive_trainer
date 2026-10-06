"""The lifecycle every ``background_jobs`` row shares: claim, run, record the outcome.

Mirrors :func:`app.generation.rounds.run_round`, which already runs question rounds this way:
the job opens its own session (the request's is closed by the time it runs), claims the row
with an atomic ``QUEUED -> RUNNING`` update so a repeated submission is harmless, and ends
``DONE`` with its result or ``FAILED`` with an error in the professor's terms. A job the
professor cancelled stops after the question in flight and ends ``FAILED`` with
``cancel_requested_at`` set (:mod:`app.jobs.cancel`). It never raises out of the task.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.domain.enums import JobKind, RoundStatus
from app.errors import AdaptiveTrainerError
from app.jobs.cancel import CANCELLED, JobCancelled, raise_if_cancelled
from app.persistence.models import BackgroundJobRow

logger = logging.getLogger(__name__)

#: What a job body gets to report progress: call it once per question committed.
Progress = Callable[[], None]

#: A job body: does the work on ``session`` for ``row`` and returns the JSON result to store.
JobBody = Callable[[Session, BackgroundJobRow, Progress], dict]


def create_job(
    session: Session,
    *,
    kind: JobKind,
    title: str,
    total: int,
    request: dict,
    course_id: int | None,
    run_id: str | None = None,
) -> BackgroundJobRow:
    """Add a ``QUEUED`` job. The caller commits, then submits the body to the queue."""
    row = BackgroundJobRow(
        kind=kind,
        title=title,
        total=total,
        request=request,
        course_id=course_id,
        run_id=run_id,
        status=RoundStatus.QUEUED,
    )
    session.add(row)
    session.flush()
    return row


def execute(
    job_id: int,
    body: JobBody,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Run ``body`` for a queued job and record how it ended."""
    if session_factory is None:
        from app.persistence.database import get_session_factory

        session_factory = get_session_factory()
    session = session_factory()
    try:
        claimed = session.execute(
            update(BackgroundJobRow)
            .where(BackgroundJobRow.id == job_id, BackgroundJobRow.status == RoundStatus.QUEUED)
            .values(status=RoundStatus.RUNNING, started_at=datetime.now(UTC))
        )
        if claimed.rowcount != 1:
            session.rollback()
            logger.info("job %s is not queued; not running it", job_id)
            return
        session.commit()
        row = session.get(BackgroundJobRow, job_id)
        assert row is not None

        def progress() -> None:
            # The body has just committed a question; count it in its own commit so the
            # Jobs panel sees it, and so a later failure cannot roll the count back.
            row.done += 1
            session.commit()
            raise_if_cancelled(session, row)

        result = body(session, row, progress)
        row.status = RoundStatus.DONE
        row.result = result
        row.finished_at = datetime.now(UTC)
        session.commit()
    except JobCancelled:
        session.rollback()
        row = session.get(BackgroundJobRow, job_id)
        if row is not None:
            row.status = RoundStatus.FAILED
            row.error = CANCELLED
            row.finished_at = datetime.now(UTC)
            session.commit()
        logger.info("job %s cancelled", job_id)
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        session.rollback()
        message = (
            exc.message
            if isinstance(exc, AdaptiveTrainerError)
            else f"The job stopped unexpectedly ({type(exc).__name__})."
        )
        try:
            row = session.get(BackgroundJobRow, job_id)
            if row is not None:
                row.status = RoundStatus.FAILED
                row.error = message
                row.finished_at = datetime.now(UTC)
                session.commit()
        except Exception:
            logger.exception("job %s: could not record the failure", job_id)
            session.rollback()
    finally:
        session.close()
