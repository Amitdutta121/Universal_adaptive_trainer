"""Video clips as tutorial blocks (Phase 7, Task 31).

A clip is one transcript chunk of a course's YouTube video: the chunk the subtopic retrieves best.
Chunks start and end on sentence boundaries (``app/ingestion/youtube.py``), so the clip does too;
it is padded a little either side so the first and last words are not clipped. No model is
called: the payload is the video id, the range and the words said in it.

A video that later goes private or stops allowing embeds is flagged by the periodic check, and
its clips are left out of student runs rather than shown as a broken player.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import TutorialRenderer
from app.persistence.models import BookRow, ChunkRow, TutorialBlockRow
from app.retrieval.chunks import UNPLAYABLE
from app.tutorials.renderers import VideoClipPayload

#: Seconds added before and after the chunk's sentences.
CLIP_PAD_SECONDS = 1.5


def clip_payload(chunk: ChunkRow) -> dict[str, Any]:
    """The ``video_clip`` payload of one video chunk.

    Raises:
        ValueError: the chunk is not a timed chunk of a YouTube source.
    """
    book = chunk.book
    if book.video_id is None or chunk.start_seconds is None or chunk.end_seconds is None:
        raise ValueError(f"Chunk {chunk.id} is not a timed chunk of a YouTube video.")
    return VideoClipPayload(
        video_id=book.video_id,
        start=round(max(0.0, chunk.start_seconds - CLIP_PAD_SECONDS), 2),
        end=round(chunk.end_seconds + CLIP_PAD_SECONDS, 2),
        title=book.title,
        transcript=chunk.text,
    ).model_dump(mode="json")


def playable(session: Session, blocks: list[TutorialBlockRow]) -> list[TutorialBlockRow]:
    """``blocks`` without the clips of videos that are flagged unplayable."""
    video_ids = {
        block.payload.get("video_id")
        for block in blocks
        if block.renderer is TutorialRenderer.VIDEO_CLIP
    }
    if not video_ids:
        return blocks
    gone = set(
        session.scalars(
            select(BookRow.video_id).where(
                BookRow.video_id.in_(video_ids), BookRow.video_availability.in_(UNPLAYABLE)
            )
        )
    )
    return [
        block
        for block in blocks
        if block.renderer is not TutorialRenderer.VIDEO_CLIP
        or block.payload.get("video_id") not in gone
    ]
