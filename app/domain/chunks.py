"""The chunk: the one source unit generation, retrieval and citations point at.

A chunk is a short run of a book's text (a few hundred words) with where it came from:
the book, the import version, a page range and the heading path above it. It replaces the
chapter/section tree as the unit everything cites (``tasks/plan.md``, Phase 1).

Two rules keep a stored chunk id meaningful for as long as anything refers to it:

1. Chunks are never edited in place. Re-importing a changed file writes a new
   ``book_version``; the old version's chunks stay, so a frozen question set still resolves.
2. The id is a hash of the book, version, position and text, so the same import always
   produces the same ids.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict

from app.domain.enums import ChunkSourceKind

#: Joins a heading path for display, with a single right angle quote.
HEADING_SEPARATOR = " \u203a "


def make_chunk_id(book_id: int, book_version: int, ordinal: int, text: str) -> str:
    """The deterministic id of one chunk: 32 hex characters of a SHA-256."""
    key = f"{book_id}\x1f{book_version}\x1f{ordinal}\x1f{text}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def page_range_label(start: int | None, end: int | None) -> str | None:
    """``Page 3`` / ``Pages 3-4`` (en dash), or ``None`` when the source has no pages (DOCX)."""
    if start is None:
        return None
    if end is None or end == start:
        return f"Page {start}"
    return f"Pages {start}\u2013{end}"


def clock(seconds: float) -> str:
    """``75.4`` -> ``1:15``; ``3725`` -> ``1:02:05``."""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def time_range_label(start: float | None, end: float | None) -> str | None:
    """``1:15-2:03`` (en dash) for a video chunk, or ``None`` when it has no times."""
    if start is None:
        return None
    return clock(start) if end is None else f"{clock(start)}\u2013{clock(end)}"


class Chunk(BaseModel):
    """One stored chunk, as the rest of the application reads it."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    book_id: int
    book_version: int
    ordinal: int
    page_start: int | None = None
    page_end: int | None = None
    heading_path: list[str] = []
    text: str
    source_kind: ChunkSourceKind = ChunkSourceKind.BOOK
    start_seconds: float | None = None
    end_seconds: float | None = None
    #: Filled in when the chunk is read with its book, for citations.
    book_title: str | None = None

    @property
    def heading_label(self) -> str | None:
        return HEADING_SEPARATOR.join(self.heading_path) or None

    @property
    def location_label(self) -> str | None:
        if self.source_kind is ChunkSourceKind.VIDEO:
            return time_range_label(self.start_seconds, self.end_seconds)
        return page_range_label(self.page_start, self.page_end)

    @property
    def label(self) -> str:
        """A short name for lists: the nearest heading, else the pages, else the position."""
        if self.heading_path:
            return self.heading_path[-1]
        return self.location_label or f"Chunk {self.ordinal + 1}"

    def citation(self) -> str:
        """``Book, 4. Repetitions > 4.4. Nested Loops (Page 33)``.

        Degrades to the book and pages when the chunk sits under no heading.
        """
        head = ", ".join(part for part in (self.book_title, self.heading_label) if part)
        location = self.location_label
        if location:
            return f"{head} ({location})" if head else location
        return head or f"Chunk {self.ordinal + 1}"
