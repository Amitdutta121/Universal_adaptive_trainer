"""Chunk embeddings and chunk retrieval (Task 6).

``ChunkEmbeddingStore`` owns ``chunk_embeddings``: one vector per (chunk, embedding
model), filled lazily for whatever is missing, so switching the embedding model embeds
afresh and the same model reuses the cache. Only a book's current version is searched.

``ChunkRetriever`` ranks chunks by dense cosine or, with ``hybrid`` (the default, from
``CHUNK_RETRIEVAL_MODE``), by LlamaIndex's fusion of the cosine ranking with BM25 over the
same text (``app.retrieval.fusion``, Task 11). A chunk is embedded, and BM25-indexed, with
its heading path prepended, which beat raw text in the
parse spike (``docs/PARSE_SPIKE.md``).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.chunks import HEADING_SEPARATOR
from app.persistence.models import (
    BookRow,
    ChunkEmbeddingRow,
    ChunkRow,
    CurriculumVersionRow,
    SubtopicRow,
)
from app.persistence.repositories import ChunkRepository, CurriculumRepository
from app.retrieval.embedder import Embedder
from app.retrieval.fusion import fused_ranking

#: Chunks embedded and committed together, so a provider failure keeps finished groups.
_COMMIT_EVERY = 64
#: Characters of chunk text a search result carries.
SNIPPET_CHARS = 300


def subtopic_query_text(subtopic: SubtopicRow) -> str:
    """The string handed to retrieval for a subtopic.

    ``"{topic} - {subtopic}: {description}"`` -- the representation that scored
    hit@1 0.85 on the taxonomy benchmark, versus 0.65 for the name alone.
    """
    head = f"{subtopic.topic.name} - {subtopic.name}"
    return f"{head}: {subtopic.description}" if subtopic.description else head


def embedding_text(chunk: ChunkRow) -> str:
    """What is embedded for a chunk: its heading path, a blank line, then its text."""
    heading = HEADING_SEPARATOR.join(chunk.heading_path or [])
    return f"{heading}\n\n{chunk.text}" if heading else chunk.text


@dataclass(frozen=True)
class ChunkVectors:
    """Row-normalised chunk vectors, aligned with ``chunk_ids``."""

    chunk_ids: list[str]
    matrix: np.ndarray  # shape (n, dim), float32, each row L2-normalised

    def __len__(self) -> int:
        return len(self.chunk_ids)


class ChunkEmbeddingStore:
    def __init__(self, session: Session, embedder: Embedder) -> None:
        self._session = session
        self._embedder = embedder

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    def missing(self, book_ids: Sequence[int] | None = None) -> list[ChunkRow]:
        """Current-version chunks with text and no vector in this embedder's model."""
        embedded = select(ChunkEmbeddingRow.chunk_id).where(
            ChunkEmbeddingRow.model == self._embedder.model
        )
        stmt = (
            select(ChunkRow)
            .where(ChunkRow.id.in_(ChunkRepository(self._session).current_ids(book_ids)))
            .where(ChunkRow.id.not_in(embedded))
            .order_by(ChunkRow.book_id, ChunkRow.ordinal)
        )
        return [row for row in self._session.scalars(stmt) if row.text.strip()]

    def backfill(self, book_ids: Sequence[int] | None = None) -> int:
        """Embed every missing chunk; returns how many were embedded.

        Commits per group (ADR-032): a provider failure late in a large book keeps the
        vectors already paid for, and the next call finishes the rest.
        """
        pending = self.missing(book_ids)
        for start in range(0, len(pending), _COMMIT_EVERY):
            group = pending[start : start + _COMMIT_EVERY]
            texts = [embedding_text(chunk) for chunk in group]
            vectors = self._embedder.embed(texts)
            for chunk, text, vector in zip(group, texts, vectors, strict=True):
                arr = np.asarray(vector, dtype=np.float32)
                self._session.add(
                    ChunkEmbeddingRow(
                        chunk_id=chunk.id,
                        model=self._embedder.model,
                        dim=int(arr.shape[0]),
                        vector=arr.tobytes(),
                        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    )
                )
            self._session.commit()
        return len(pending)

    def load(self, book_ids: Sequence[int] | None = None) -> ChunkVectors:
        """Every current-version vector in this embedder's model, normalised."""
        if book_ids is not None and not book_ids:
            return ChunkVectors([], np.empty((0, 0), dtype=np.float32))
        stmt = (
            select(ChunkEmbeddingRow.chunk_id, ChunkEmbeddingRow.vector)
            .where(
                ChunkEmbeddingRow.model == self._embedder.model,
                ChunkEmbeddingRow.chunk_id.in_(
                    ChunkRepository(self._session).current_ids(book_ids)
                ),
            )
            .order_by(ChunkEmbeddingRow.chunk_id)
        )
        ids: list[str] = []
        rows: list[np.ndarray] = []
        for chunk_id, blob in self._session.execute(stmt):
            ids.append(chunk_id)
            rows.append(np.frombuffer(blob, dtype=np.float32))
        if not rows:
            return ChunkVectors([], np.empty((0, 0), dtype=np.float32))
        matrix = np.vstack(rows)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return ChunkVectors(chunk_ids=ids, matrix=(matrix / norms).astype(np.float32))


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    book_id: int
    book_title: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    score: float
    snippet: str


class ChunkRetriever:
    def __init__(
        self, session: Session, store: ChunkEmbeddingStore, *, hybrid: bool | None = None
    ) -> None:
        """``hybrid`` defaults to ``CHUNK_RETRIEVAL_MODE``."""
        self._session = session
        self._store = store
        self._hybrid = get_settings().chunk_retrieval_mode == "hybrid" if hybrid is None else hybrid

    def search(
        self, query: str, *, book_ids: list[int] | None = None, top_k: int = 5
    ) -> list[RetrievedChunk]:
        """The ``top_k`` current chunks most similar to ``query``, best first.

        Embeds any chunk still missing a vector in the current model first. ``score`` is
        always the cosine, also in hybrid mode, so callers' cosine floors keep their meaning.
        """
        self._store.backfill(book_ids)
        loaded = self._store.load(book_ids)
        if len(loaded) == 0:
            return []
        query_vector = np.asarray(self._store.embedder.embed([query])[0], dtype=np.float32)
        norm = float(np.linalg.norm(query_vector))
        if norm == 0.0:
            return []
        sims = loaded.matrix @ (query_vector / norm)
        if self._hybrid:
            return self._fused(query, loaded, sims, top_k)
        k = min(top_k, sims.shape[0])
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        rows = ChunkRepository(self._session).get_many([loaded.chunk_ids[i] for i in top])
        return [
            _to_result(rows[loaded.chunk_ids[i]], float(sims[i]))
            for i in top
            if loaded.chunk_ids[i] in rows
        ]

    def _fused(
        self, query: str, loaded: ChunkVectors, sims: np.ndarray, top_k: int
    ) -> list[RetrievedChunk]:
        rows = ChunkRepository(self._session).get_many(loaded.chunk_ids)
        ids = [chunk_id for chunk_id in loaded.chunk_ids if chunk_id in rows]
        position = {chunk_id: i for i, chunk_id in enumerate(loaded.chunk_ids)}
        dense = sorted(ids, key=lambda chunk_id: -sims[position[chunk_id]])
        ranked = [(c, embedding_text(rows[c]), float(sims[position[c]])) for c in dense]
        return [
            _to_result(rows[chunk_id], float(sims[position[chunk_id]]))
            for chunk_id in fused_ranking(query, ranked, top_k=top_k)
        ]

    def for_subtopic(
        self, subtopic_id: int, *, top_k: int = 5, book_ids: list[int] | None = None
    ) -> list[RetrievedChunk]:
        """Chunks for a subtopic: from its taxonomy's source books, else ``book_ids``, else the
        books of the taxonomy's own course -- never another course's books (ADR-060)."""
        subtopic = CurriculumRepository(self._session).get_subtopic(subtopic_id)
        version = self._session.get(CurriculumVersionRow, subtopic.topic.curriculum_version_id)
        if version and version.source_book_ids:
            scoped: list[int] | None = list(version.source_book_ids)
        elif book_ids is not None:
            scoped = book_ids
        else:
            scoped = course_book_ids(self._session, version.course_id if version else None)
        return self.search(subtopic_query_text(subtopic), book_ids=scoped, top_k=top_k)


def course_book_ids(session: Session, course_id: int | None) -> list[int] | None:
    """The course's book ids, or ``None`` (every book) outside a course."""
    if course_id is None:
        return None
    return list(session.scalars(select(BookRow.id).where(BookRow.course_id == course_id)))


def _to_result(row: ChunkRow, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.id,
        book_id=row.book_id,
        book_title=row.book.title,
        heading_path=list(row.heading_path or []),
        page_start=row.page_start,
        page_end=row.page_end,
        score=round(score, 4),
        snippet=" ".join(row.text.split())[:SNIPPET_CHARS],
    )
