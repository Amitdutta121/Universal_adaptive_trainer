"""Where a route hands work to run after its response.

Every background job goes through :class:`JobQueue`, so the executor is one swap: today
:class:`BackgroundTasksQueue` runs work in this process after the response is sent. A
durable queue (Huey, RQ, ...) would be another implementation returned by
:func:`get_job_queue`, with no change to the routes that submit or the functions they submit.

That swap holds because a submitted function takes ids, not live objects: it opens its own
session and reloads its row. The optional ``client`` / ``embedder`` arguments some
functions accept are test seams; production routes pass ``None`` (or the dependency's
default), which a serialising queue can carry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Protocol

from fastapi import BackgroundTasks, Depends


class JobQueue(Protocol):
    """Runs ``func(*args, **kwargs)`` later, outside the request that submitted it."""

    def submit(self, func: Callable[..., None], /, *args: Any, **kwargs: Any) -> None: ...


class BackgroundTasksQueue:
    """Runs submitted work in this process once the response has been sent.

    Not durable: work queued or running when the process stops is lost, and
    :mod:`app.jobs.recovery` marks its row failed on the next start.
    """

    def __init__(self, tasks: BackgroundTasks) -> None:
        self._tasks = tasks

    def submit(self, func: Callable[..., None], /, *args: Any, **kwargs: Any) -> None:
        self._tasks.add_task(func, *args, **kwargs)


def get_job_queue(background: BackgroundTasks) -> JobQueue:
    """The queue routes submit to. Override this dependency to change the executor."""
    return BackgroundTasksQueue(background)


JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]
