"""Ranking book sections against a query, and against a subtopic.

Dense cosine over the section embedding index (see :mod:`app.retrieval.store`).
No BM25, no reranker: on the taxonomy retrieval benchmark those did not improve
hit@k over plain dense search, and the review queue is the backstop for the rest.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.persistence.models import (
    BookSectionRow,
    CurriculumVersionRow,
    SubtopicRow,
)
from app.persistence.repositories import CurriculumRepository
from app.retrieval.store import SectionEmbeddingStore

SNIPPET_CHARS = 300


@dataclass(frozen=True)
class RetrievedSection:
    section_id: int
    book_id: int
    book_title: str
    chapter_title: str | None
    section_number: str | None
    section_title: str | None
    score: float
    snippet: str


def subtopic_query_text(subtopic: SubtopicRow) -> str:
    """The string handed to retrieval for a subtopic.

    ``"{topic} - {subtopic}: {description}"`` -- the representation that scored
    hit@1 0.85 on the taxonomy benchmark, versus 0.65 for the name alone.
    """
    head = f"{subtopic.topic.name} - {subtopic.name}"
    return f"{head}: {subtopic.description}" if subtopic.description else head


class SectionRetriever:
    def __init__(self, session: Session, store: SectionEmbeddingStore) -> None:
        self._session = session
        self._store = store

    def search(
        self,
        query: str,
        *,
        book_ids: list[int] | None = None,
        top_k: int = 5,
    ) -> list[RetrievedSection]:
        loaded = self._store.load(book_ids=book_ids)
        if len(loaded) == 0:
            return []

        query_vector = np.asarray(self._store.embedder.embed([query])[0], dtype=np.float32)
        norm = float(np.linalg.norm(query_vector))
        if norm == 0.0:
            return []
        sims = loaded.matrix @ (query_vector / norm)

        k = min(top_k, sims.shape[0])
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        ranked_ids = [loaded.section_ids[i] for i in top]

        rows = self._sections_by_id(ranked_ids)
        return [
            self._to_result(rows[section_id], float(sims[i]))
            for section_id, i in zip(ranked_ids, top, strict=True)
            if section_id in rows
        ]

    def for_subtopic(self, subtopic_id: int, *, top_k: int = 5) -> list[RetrievedSection]:
        subtopic = CurriculumRepository(self._session).get_subtopic(subtopic_id)
        version = self._session.get(CurriculumVersionRow, subtopic.topic.curriculum_version_id)
        scoped = list(version.source_book_ids) if version and version.source_book_ids else None
        return self.search(subtopic_query_text(subtopic), book_ids=scoped, top_k=top_k)

    # -- internals --------------------------------------------------------

    def _sections_by_id(self, ids: list[int]) -> dict[int, BookSectionRow]:
        if not ids:
            return {}
        stmt = (
            select(BookSectionRow)
            .options(joinedload(BookSectionRow.chapter), joinedload(BookSectionRow.book))
            .where(BookSectionRow.id.in_(ids))
        )
        return {row.id: row for row in self._session.scalars(stmt)}

    @staticmethod
    def _to_result(row: BookSectionRow, score: float) -> RetrievedSection:
        snippet = " ".join((row.text or "").split())[:SNIPPET_CHARS]
        return RetrievedSection(
            section_id=row.id,
            book_id=row.book_id,
            book_title=row.book.title,
            chapter_title=row.chapter.title if row.chapter else None,
            section_number=row.number,
            section_title=row.title,
            score=round(score, 4),
            snippet=snippet,
        )
