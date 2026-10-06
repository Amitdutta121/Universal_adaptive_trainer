"""Collects judge re-run results without anyone pressing "poll".

A judge re-run is a provider batch that finishes up to 24 hours after it is submitted
(ADR-030). :func:`collect_pending_judge_runs` asks the provider about every unfinished
run once and records what has finished -- the same work ``POST
/evaluation/batch-runs/{run_id}/poll`` does for one run. :class:`JudgeCollector` calls
it on a timer from app startup, so a run is collected after submission and after a
restart alike. With a durable queue this would be a periodic task calling the same
function.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import JudgeBatchStatus
from app.evaluation.batch_service import poll_and_ingest
from app.persistence.models import JudgeBatchRunRow

logger = logging.getLogger(__name__)

#: Provider batches take minutes to hours; checking every minute is ample.
POLL_SECONDS = 60.0

_UNFINISHED = (JudgeBatchStatus.SUBMITTED, JudgeBatchStatus.IN_PROGRESS)


def collect_pending_judge_runs(
    session_factory: Callable[[], Session] | None = None,
    *,
    poll: Callable[[Session, str], object] = poll_and_ingest,
) -> int:
    """Poll every unfinished judge run once. Returns how many were polled.

    One run failing to poll (provider down, bad credential) is logged and left for the
    next pass; it never stops the others.
    """
    if session_factory is None:
        from app.persistence.database import get_session_factory

        session_factory = get_session_factory()
    with session_factory() as session:
        run_ids = list(
            session.scalars(
                select(JudgeBatchRunRow.run_id).where(JudgeBatchRunRow.status.in_(_UNFINISHED))
            )
        )
    for run_id in run_ids:
        with session_factory() as session:
            try:
                poll(session, run_id)
                session.commit()
            except Exception:
                session.rollback()
                logger.warning("judge run %s: could not collect results", run_id, exc_info=True)
    return len(run_ids)


class JudgeCollector:
    """A daemon thread that runs :func:`collect_pending_judge_runs` every ``interval``."""

    def __init__(self, interval: float = POLL_SECONDS) -> None:
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="judge-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # Waits first: at startup the app has only just come up, and a run submitted a
        # moment ago has nothing to collect yet.
        while not self._stop.wait(self._interval):
            try:
                collect_pending_judge_runs()
            except Exception:
                logger.exception("judge collector pass failed")
