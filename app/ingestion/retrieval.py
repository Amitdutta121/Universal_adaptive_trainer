"""Source retrieval: reading chunks back out, with citations.

This is the interface question generation and the judges use to fetch grounding text. It
returns domain objects rather than ORM rows, and every chunk it hands out can cite the
book, heading path and pages it came from (:meth:`app.domain.chunks.Chunk.citation`).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.chunks import Chunk
from app.persistence.models import ChunkRow
from app.persistence.repositories import ChunkRepository


def chunk_from_row(row: ChunkRow) -> Chunk:
    """Convert a chunk row, with its book loaded, into its domain form."""
    chunk = Chunk.model_validate(row)
    return chunk.model_copy(update={"book_title": row.book.title})


class SourceRetrieval:
    """Reads a book's chunks for grounding and display."""

    def __init__(self, session: Session) -> None:
        self._chunks = ChunkRepository(session)

    def get_chunk(self, chunk_id: str) -> Chunk:
        """One chunk of any version, with its book title for citation.

        Raises:
            NotFoundError: if no such chunk exists.
        """
        return chunk_from_row(self._chunks.get(chunk_id))

    def chunks_in_book(self, book_id: int, *, page: int | None = None) -> list[Chunk]:
        """The current version's chunks in reading order; with ``page``, those covering it."""
        return [chunk_from_row(row) for row in self._chunks.list_for_book(book_id, page=page)]
