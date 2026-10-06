"""Stopping a running job between questions.

Cancelling only records *when the professor asked* (``cancel_requested_at``). The loop doing
the work checks it after each committed question or target and raises
:class:`JobCancelled`, so the question in flight -- already paid for -- is finished and kept,
and nothing after it is started. A job still queued is ended at once by the cancel itself.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import BackgroundJobRow, GenerationRoundRow


class JobCancelled(Exception):
    """Raised inside a job's loop when the professor asked it to stop."""


#: What a cancelled job or round says in place of an error. No count: the progress counter
#: already shows it, and for a coverage fill it counts gap cells, not questions.
CANCELLED = "Cancelled. Everything made before it stopped is kept."


def raise_if_cancelled(session: Session, row: BackgroundJobRow | GenerationRoundRow) -> None:
    """Raise :class:`JobCancelled` when a stop was asked for since the job started.

    Reads the column fresh: the cancel arrives on another request's session, after this one
    loaded the row.
    """
    model = type(row)
    asked = session.scalar(select(model.cancel_requested_at).where(model.id == row.id))
    if asked is not None:
        raise JobCancelled
