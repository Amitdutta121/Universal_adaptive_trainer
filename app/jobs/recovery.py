"""What a restart does to jobs that were in flight.

:class:`~app.jobs.queue.BackgroundTasksQueue` runs work in this process, so a job queued
or running when the process stopped will never finish. Left as it was, it would show as
running forever -- and a stuck question round blocks every later round of its taxonomy
(``app.generation.rounds.active_round``). On startup they are marked failed instead; the
questions they already committed stay.

Assumes one backend process (the Dockerfile runs a single uvicorn worker): a second
process starting up would otherwise fail the first one's live jobs. Judge re-runs are not
touched here -- the provider is still working on them, and
:mod:`app.jobs.judge_collector` picks them back up.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.domain.enums import RoundStatus
from app.persistence.models import BackgroundJobRow, GenerationRoundRow

logger = logging.getLogger(__name__)

INTERRUPTED = "Interrupted by a server restart. Questions already made are kept."

_IN_FLIGHT = (RoundStatus.QUEUED, RoundStatus.RUNNING)


def fail_interrupted_jobs(session_factory: Callable[[], Session] | None = None) -> int:
    """Mark every queued or running job and question round failed. Returns how many."""
    if session_factory is None:
        from app.persistence.database import get_session_factory

        session_factory = get_session_factory()
    now = datetime.now(UTC)
    with session_factory() as session:
        changed = 0
        for model in (BackgroundJobRow, GenerationRoundRow):
            result = session.execute(
                update(model)
                .where(model.status.in_(_IN_FLIGHT))
                .values(status=RoundStatus.FAILED, error=INTERRUPTED, finished_at=now)
            )
            changed += result.rowcount
        session.commit()
    if changed:
        logger.warning("marked %d interrupted job(s) as failed after a restart", changed)
    return changed
