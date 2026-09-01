"""Building and loading the section embedding index.

The store owns the ``section_embeddings`` table: it fills it from
``book_sections.text`` (idempotently, keyed on a content hash) and loads it back
into memory as a plain float32 matrix for cosine search. At ~1,600 sections the
whole matrix is ~10 MB, so there is no vector database here on purpose.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import BookSectionRow, SectionEmbeddingRow
from app.persistence.repositories import BookRepository
from app.retrieval.embedder import Embedder

#: Sections embedded and committed together during a backfill.
_COMMIT_EVERY = 64


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BackfillResult:
    embedded: int
    skipped: int
    total: int
    empty: int = 0

    def summary(self) -> str:
        return f"embedded {self.embedded} / skipped {self.skipped} / total {self.total}" + (
            f" ({self.empty} empty sections ignored)" if self.empty else ""
        )


@dataclass(frozen=True)
class LoadedVectors:
    """Row-normalised section vectors, aligned with ``section_ids``."""

    section_ids: list[int]
    matrix: np.ndarray  # shape (n, dim), float32, each row L2-normalised

    def __len__(self) -> int:
        return len(self.section_ids)


class SectionEmbeddingStore:
    def __init__(self, session: Session, embedder: Embedder) -> None:
        self._session = session
        self._embedder = embedder

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    # -- build ----------------------------------------------------------------

    def backfill(
        self,
        *,
        book_ids: Sequence[int] | None = None,
        rebuild: bool = False,
        dry_run: bool = False,
    ) -> BackfillResult:
        """Embed every section of the selected books that is new or changed.

        Idempotent: a section whose text hash and model already match an existing
        row is skipped. ``rebuild`` re-embeds regardless. ``dry_run`` reports the
        counts without calling the provider or writing rows.
        """
        sections = list(self._sections(book_ids))
        existing = self._existing_rows(section.id for section in sections)

        pending: list[BookSectionRow] = []
        hashes: dict[int, str] = {}
        empty = 0
        for section in sections:
            text = (section.text or "").strip()
            if not text:
                empty += 1
                continue
            digest = content_hash(section.text)
            hashes[section.id] = digest
            row = existing.get(section.id)
            fresh = (
                row is not None
                and not rebuild
                and row.content_hash == digest
                and row.model == self._embedder.model
            )
            if not fresh:
                pending.append(section)

        total = len(sections) - empty
        skipped = total - len(pending)
        if dry_run:
            return BackfillResult(embedded=len(pending), skipped=skipped, total=total, empty=empty)
        if not pending:
            return BackfillResult(embedded=0, skipped=total, total=total, empty=empty)

        # Commit per group so a provider failure late in a large backfill keeps
        # the sections already embedded (the run is idempotent, so a re-run
        # finishes the rest). Mirrors ADR-032's per-unit commit in generation.
        done = 0
        for start in range(0, len(pending), _COMMIT_EVERY):
            group = pending[start : start + _COMMIT_EVERY]
            vectors = self._embedder.embed([section.text for section in group])
            for section, vector in zip(group, vectors, strict=True):
                arr = np.asarray(vector, dtype=np.float32)
                row = existing.get(section.id)
                if row is None:
                    row = SectionEmbeddingRow(section_id=section.id)
                    self._session.add(row)
                row.model = self._embedder.model
                row.dim = int(arr.shape[0])
                row.vector = arr.tobytes()
                row.content_hash = hashes[section.id]
            self._session.commit()
            done += len(group)
        return BackfillResult(embedded=done, skipped=skipped, total=total, empty=empty)

    # -- load ---------------------------------------------------------------

    def load(self, *, book_ids: Sequence[int] | None = None) -> LoadedVectors:
        """Every stored vector (optionally restricted to some books), normalised."""
        stmt = select(SectionEmbeddingRow.section_id, SectionEmbeddingRow.vector)
        if book_ids is not None:
            allowed = list(book_ids)
            if not allowed:
                return LoadedVectors([], np.empty((0, 0), dtype=np.float32))
            stmt = stmt.join(
                BookSectionRow, BookSectionRow.id == SectionEmbeddingRow.section_id
            ).where(BookSectionRow.book_id.in_(allowed))

        ids: list[int] = []
        rows: list[np.ndarray] = []
        for section_id, blob in self._session.execute(stmt):
            ids.append(int(section_id))
            rows.append(np.frombuffer(blob, dtype=np.float32))
        if not rows:
            return LoadedVectors([], np.empty((0, 0), dtype=np.float32))

        matrix = np.vstack(rows)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return LoadedVectors(section_ids=ids, matrix=(matrix / norms).astype(np.float32))

    # -- internals --------------------------------------------------------

    def _sections(self, book_ids: Sequence[int] | None) -> Iterable[BookSectionRow]:
        allowed = (
            set(book_ids)
            if book_ids is not None
            else {book.id for book in BookRepository(self._session).list_usable()}
        )
        if not allowed:
            return []
        stmt = (
            select(BookSectionRow)
            .where(BookSectionRow.book_id.in_(allowed))
            .order_by(BookSectionRow.book_id, BookSectionRow.position, BookSectionRow.id)
        )
        return list(self._session.scalars(stmt))

    def _existing_rows(self, section_ids: Iterable[int]) -> dict[int, SectionEmbeddingRow]:
        ids = list(section_ids)
        if not ids:
            return {}
        stmt = select(SectionEmbeddingRow).where(SectionEmbeddingRow.section_id.in_(ids))
        return {row.section_id: row for row in self._session.scalars(stmt)}
