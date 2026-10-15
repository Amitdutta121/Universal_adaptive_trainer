"""Flags YouTube sources that went private, were deleted or stopped allowing embeds (Task 30).

:func:`check_video_sources` asks YouTube's oEmbed endpoint about every YouTube source once and
records the answer on the book row; clips of a video that is not ``AVAILABLE`` are then left out
of student runs (``app/tutorials/serving.py``). :class:`VideoAvailabilityChecker` calls it on a
timer from app startup, like :class:`~app.jobs.judge_collector.JudgeCollector`.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import SourceFormat, VideoAvailability
from app.ingestion.youtube import AvailabilityCheck, check_availability
from app.persistence.models import BookRow

logger = logging.getLogger(__name__)

#: Videos rarely change state; a few checks a day is ample and stays far from rate limits.
CHECK_SECONDS = 6 * 3600.0


def check_video_sources(
    session_factory: Callable[[], Session] | None = None,
    *,
    check: AvailabilityCheck = check_availability,
) -> dict[int, VideoAvailability]:
    """Check every YouTube source once. Returns each book's availability after the pass.

    An ``UNKNOWN`` answer (YouTube unreachable) keeps the earlier answer, so a network blip
    never hides a playable clip; only the check time moves on.
    """
    if session_factory is None:
        from app.persistence.database import get_session_factory

        session_factory = get_session_factory()
    result: dict[int, VideoAvailability] = {}
    with session_factory() as session:
        books = session.scalars(
            select(BookRow).where(
                BookRow.source_format == SourceFormat.YOUTUBE, BookRow.video_id.is_not(None)
            )
        ).all()
        for book in books:
            availability, _ = check(book.video_id or "")
            if availability is not VideoAvailability.UNKNOWN or book.video_availability is None:
                if book.video_availability != availability:
                    logger.info(
                        "Video %s (book %s) is now %s", book.video_id, book.id, availability
                    )
                book.video_availability = availability
            book.availability_checked_at = datetime.now(UTC)
            result[book.id] = book.video_availability or VideoAvailability.UNKNOWN
        session.commit()
    return result


class VideoAvailabilityChecker:
    """A daemon thread that runs :func:`check_video_sources` every ``interval``."""

    def __init__(self, interval: float = CHECK_SECONDS) -> None:
        self._interval = interval
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._loop, name="video-availability", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # Waits first: every video was checked when it was imported.
        while not self._stop.wait(self._interval):
            try:
                check_video_sources()
            except Exception:
                logger.exception("video availability pass failed")
