"""A video transcript becomes timestamped chunks retrieval reads like a book's (Phase 7, T29/T30).

Lecture upload and Whisper are out of scope (decided 2026-10-15: YouTube only); the timed
chunking and retrieval they would share is tested here on a fixture transcript.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

import book_documents as docs
from sqlalchemy.orm import Session

from app.domain.chunks import Chunk
from app.domain.enums import ChunkSourceKind, VideoAvailability
from app.ingestion.youtube import Segment, YouTubeImportService, chunk_segments
from app.persistence.repositories import ChunkRepository
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "lecture_transcript.json").read_text(encoding="utf-8")
)
SEGMENTS = [Segment(s["start"], s["duration"], s["text"]) for s in FIXTURE["segments"]]
VIDEO_ID = FIXTURE["video_id"]


def _available(_video_id: str) -> tuple[VideoAvailability, str | None]:
    return VideoAvailability.AVAILABLE, "Loops in Python"


def _import(session: Session, course_id: int | None = None):
    book = YouTubeImportService(session, fetch=lambda _id: SEGMENTS, check=_available).import_video(
        f"https://youtu.be/{VIDEO_ID}", course_id=course_id
    )
    session.commit()
    return book


def test_chunks_have_monotonic_non_overlapping_timestamps() -> None:
    chunks = chunk_segments(SEGMENTS, target_words=40, max_words=120)

    assert len(chunks) >= 4
    assert chunks[0].start == SEGMENTS[0].start
    for chunk in chunks:
        assert chunk.end > chunk.start
    for earlier, later in pairwise(chunks):
        assert later.start > earlier.start
        assert earlier.end == later.start  # they meet exactly: no overlap, no gap
    last = SEGMENTS[-1]
    assert chunks[-1].end <= last.start + (last.duration or 0) + 1e-6


def test_chunks_end_on_sentence_boundaries_and_keep_every_word() -> None:
    chunks = chunk_segments(SEGMENTS, target_words=40, max_words=120)

    for chunk in chunks:
        assert chunk.text.rstrip()[-1] in ".?!"
        assert chunk.text[0].isupper()
    words = [word for segment in SEGMENTS for word in segment.text.split()]
    assert " ".join(chunk.text for chunk in chunks).split() == words


def test_captions_without_punctuation_are_cut_at_the_word_limit() -> None:
    segments = [Segment(i * 2.0, 2.5, "so then we add one more item") for i in range(30)]

    chunks = chunk_segments(segments, target_words=20, max_words=50)

    assert all(len(chunk.text.split()) <= 50 for chunk in chunks)
    assert sum(len(chunk.text.split()) for chunk in chunks) == 30 * 7
    for earlier, later in pairwise(chunks):
        assert earlier.end == later.start


def test_an_imported_video_is_stored_as_video_chunks_with_times(session: Session) -> None:
    book = _import(session)

    rows = ChunkRepository(session).list_for_book(book.id)
    assert book.title == "Loops in Python"
    assert book.video_id == VIDEO_ID
    assert len(rows) >= 2
    assert {row.source_kind for row in rows} == {ChunkSourceKind.VIDEO}
    assert all(row.start_seconds is not None and row.end_seconds is not None for row in rows)
    assert [row.start_seconds for row in rows] == sorted(row.start_seconds for row in rows)
    chunk = Chunk.model_validate(rows[0])
    assert chunk.location_label == "0:01\u2013" + chunk.location_label.split("\u2013")[1]
    assert chunk.page_start is None


class LoopEmbedder:
    VOCAB = ("while", "range", "accumulator", "total", "program", "variable")
    model = "loop-v1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(t.lower().count(word)) + 0.01 for word in self.VOCAB] for t in texts]


def test_video_chunks_are_retrievable_like_book_chunks(session: Session) -> None:
    book = docs.chunked_book(session, docs.think_python())
    video = _import(session)
    for hybrid in (False, True):
        retriever = ChunkRetriever(
            session, ChunkEmbeddingStore(session, LoopEmbedder()), hybrid=hybrid
        )
        found = retriever.search("the while loop condition", top_k=3)
        assert found[0].book_id == video.id
        text = ChunkRepository(session).get_many([found[0].chunk_id])[found[0].chunk_id].text
        assert "while loop" in text.lower()
        assert {hit.book_id for hit in retriever.search("program variable", top_k=8)} >= {book.id}
