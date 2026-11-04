"""Video clips as tutorial blocks (Phase 7, Task 31).

A clip is one transcript chunk of a course's YouTube video: the chunk the subtopic retrieves best.
Chunks start and end on sentence boundaries (``app/ingestion/youtube.py``), so the clip does too;
it is padded a little either side so the first and last words are not clipped. The payload is
the video id, the range and the words said in it.

The search query is the subtopic's text plus a short passage the model writes the way a lecturer
would say it (HyDE): a syllabus line and spoken transcript share few words, and a passage in the
transcript's register ranks the stretch that explains the subtopic higher. That is the clip's
one model call; if it fails, the subtopic's text alone is the query.

A video that later goes private or stops allowing embeds is flagged by the periodic check, and
its clips are left out of student runs rather than shown as a broken player.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import TutorialRenderer
from app.errors import LLMRequestError, MalformedModelOutputError
from app.llm import StructuredLLMClient
from app.persistence.models import BookRow, ChunkRow, SubtopicRow, TutorialBlockRow
from app.retrieval.chunks import UNPLAYABLE, subtopic_query_text
from app.tutorials.renderers import VideoClipPayload

logger = logging.getLogger(__name__)

#: Seconds added before and after the chunk's sentences.
CLIP_PAD_SECONDS = 1.5

LECTURE_SYSTEM = (
    "You write what a lecturer says aloud in a recorded programming lecture. Plain spoken "
    "sentences, the way people talk when teaching: no markdown, no headings, no lists, no code "
    "blocks. Say the terms, function names and keywords a lecturer would say for this idea."
)


class LecturePassage(BaseModel):
    text: str = Field(
        description="About 80-120 words a lecturer would say while explaining the subtopic."
    )


def lecture_query(client: StructuredLLMClient, subtopic: SubtopicRow) -> tuple[str, bool]:
    """The clip search's query, and whether the model's passage is in it.

    The subtopic's own text comes first, so its terms still count when the passage drifts.
    """
    query = subtopic_query_text(subtopic)
    try:
        passage = client.complete_structured(
            system=LECTURE_SYSTEM,
            prompt=f"Explain this subtopic as you would in the lecture:\n{query}",
            response_model=LecturePassage,
        )
    except (LLMRequestError, MalformedModelOutputError) as exc:
        logger.warning("Lecture-style clip query failed; searching on the subtopic: %s", exc)
        return query, False
    text = passage.text.strip()
    return (f"{query}\n\n{text}", True) if text else (query, False)


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


def course_has_video(session: Session, course_id: int | None) -> bool:
    """Whether the course has a YouTube video a clip can be cut from (not flagged unplayable)."""
    if course_id is None:
        return False
    return (
        session.scalar(
            select(BookRow.id)
            .where(
                BookRow.course_id == course_id,
                BookRow.video_id.is_not(None),
                BookRow.video_availability.not_in(UNPLAYABLE)
                | BookRow.video_availability.is_(None),
            )
            .limit(1)
        )
        is not None
    )
