"""Is a question a duplicate of one already in the bank? (ADR-063 point 6.)

Two users. Inside a round, :class:`DuplicateChecker` is the hook
:class:`~app.generation.review.RoundReview` calls on every clean attempt: an exact match or a
cosine at or above :data:`DUPLICATE_THRESHOLD` fails the attempt, a score at or above
:data:`SIMILAR_THRESHOLD` is kept with a soft flag. After the coverage Generate run,
:func:`app.web.routes.api.dedup.flag_possible_duplicates` writes the soft flags only.

The comparison pool is the same topic, approved or validation-passed questions
(:meth:`~app.persistence.repositories.QuestionRepository.list_dedup_candidates`). The text
compared is the prompt, the code and the options (:func:`embed_text`): output-prediction
questions share one generic stem, so without the code they all look alike.

Candidate vectors are cached in ``question_embeddings`` and re-embedded only when the
question's text or the model changes, so a check costs one embedding call: the new question,
plus any candidate not yet cached, in the same request.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.questions import Question
from app.persistence.models import QuestionEmbeddingRow, QuestionRow, QuestionSimilarityRow
from app.persistence.repositories import QuestionRepository
from app.retrieval.embedder import Embedder

logger = logging.getLogger(__name__)

#: At or above this cosine a question is a duplicate: inside a round the attempt is retried
#: (on the last attempt it is kept with a flag, not dropped).
#:
#: Calibrated on a copy of the dev DB (``scripts/calibrate_dedup.py``): each reviewed question
#: scored by its max cosine (prompt + code + options) to earlier questions of the same topic;
#: 14 professor "too_similar_repetitive" rejects vs 140 approvals.
#:
#: ====== ============ =================
#: thr    rejects hit  approvals flagged
#: ====== ============ =================
#: 0.75   9/14         24/140
#: 0.80   3/14         12/140
#: 0.85   2/14         8/140
#: 0.90   1/14         4/140
#: 0.95   0/14         0/140
#: ====== ============ =================
#:
#: Without the code, 22/140 approvals scored >= 0.90. So 0.90 is the hard line (a retry costs a
#: generation call, so it must rarely hit a question the professor would approve), and the
#: 0.75--0.90 band, which holds most of the rejects, is shown to the professor as a flag.
DUPLICATE_THRESHOLD = 0.90

#: At or above this cosine a question is flagged as a possible duplicate
#: (``QuestionSimilarityRow``) but kept. See :data:`DUPLICATE_THRESHOLD` for the calibration.
SIMILAR_THRESHOLD = 0.75

#: ``QuestionSimilarityRow.model`` for a match found by text alone, without an embedder.
EXACT_MATCH_MODEL = "exact-text"


def embed_text(prompt: str | None, content: Mapping[str, Any] | None) -> str:
    """The text a question is compared on: prompt, then code, then options."""
    content = content or {}
    parts = [prompt or ""]
    code = content.get("code")
    if code:
        parts.append(str(code))
    options = content.get("options")
    if isinstance(options, list):
        parts.extend(str(option) for option in options)
    return "\n".join(parts)


def text_hash(text: str) -> str:
    """SHA-256 of ``text`` lower-cased with whitespace collapsed: the exact-match key."""
    normalised = " ".join(text.lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SimilarQuestion:
    """An existing question a new one scored at or above :data:`SIMILAR_THRESHOLD` against."""

    question_id: int
    #: The existing question's compared text, quoted back to the generator on a retry.
    text: str
    score: float
    exact: bool
    #: The vector space ``score`` was measured in, or :data:`EXACT_MATCH_MODEL`.
    model: str

    @property
    def duplicate(self) -> bool:
        """Too close to keep without a retry."""
        return self.exact or self.score >= DUPLICATE_THRESHOLD


class QuestionEmbeddingStore:
    """Cached, row-normalised vectors of stored questions (``question_embeddings``)."""

    def __init__(self, session: Session, embedder: Embedder) -> None:
        self._session = session
        self._embedder = embedder

    def embed_with(self, text: str, rows: Sequence[QuestionRow]) -> tuple[np.ndarray, np.ndarray]:
        """``text``'s vector and ``rows``' vectors, all L2-normalised, in one provider call.

        Rows whose cached vector is missing or stale (text or model changed) are embedded in
        the same request as ``text`` and their cache rows written (flushed, not committed).
        """
        texts = {row.id: embed_text(row.prompt, row.content) for row in rows}
        cached = {
            item.question_id: item
            for item in self._session.scalars(
                select(QuestionEmbeddingRow).where(
                    QuestionEmbeddingRow.question_id.in_([row.id for row in rows])
                )
            )
        }
        stale = [
            row
            for row in rows
            if (item := cached.get(row.id)) is None
            or item.model != self._embedder.model
            or item.text_hash != text_hash(texts[row.id])
        ]
        fresh = self._embedder.embed([text] + [texts[row.id] for row in stale])
        for row, vector in zip(stale, fresh[1:], strict=True):
            arr = np.asarray(vector, dtype=np.float32)
            item = cached.get(row.id)
            if item is None:
                item = QuestionEmbeddingRow(question_id=row.id)
                self._session.add(item)
                cached[row.id] = item
            item.model = self._embedder.model
            item.dim = int(arr.shape[0])
            item.vector = arr.tobytes()
            item.text_hash = text_hash(texts[row.id])
        self._session.flush()

        query = _normalised(np.asarray([fresh[0]], dtype=np.float32))[0]
        matrix = _normalised(
            np.vstack([np.frombuffer(cached[row.id].vector, dtype=np.float32) for row in rows])
        )
        return query, matrix


class DuplicateChecker:
    """Finds the stored questions a new one is too close to.

    Without an embedder only exact (normalised) matches are found. Called as a round's
    duplicate hook it never raises: an embedder failure falls back to exact matches, since a
    missed flag must not cost the round a question.
    """

    def __init__(self, session: Session, embedder: Embedder | None) -> None:
        self._session = session
        self._embedder = embedder

    def similar(
        self,
        *,
        topic_id: int | None,
        prompt: str | None,
        content: Mapping[str, Any] | None,
        exclude_ids: Collection[int] = (),
        exact_only: bool = False,
    ) -> list[SimilarQuestion]:
        """Questions of the same topic scoring at or above :data:`SIMILAR_THRESHOLD`, best first.

        No candidates means no embedder call. Raises on an embedder failure.
        """
        if topic_id is None:
            return []
        candidates = QuestionRepository(self._session).list_dedup_candidates(
            topic_id=topic_id, exclude_ids=exclude_ids
        )
        if not candidates:
            return []
        text = embed_text(prompt, content)
        key = text_hash(text)
        texts = {row.id: embed_text(row.prompt, row.content) for row in candidates}
        exact = {row.id for row in candidates if text_hash(texts[row.id]) == key}

        scores: dict[int, float] = {}
        if self._embedder is not None and not exact_only:
            query, matrix = QuestionEmbeddingStore(self._session, self._embedder).embed_with(
                text, candidates
            )
            scores = {row.id: float(s) for row, s in zip(candidates, matrix @ query, strict=True)}

        model = self._embedder.model if self._embedder is not None else EXACT_MATCH_MODEL
        found = [
            SimilarQuestion(
                question_id=row.id,
                text=texts[row.id],
                score=1.0 if row.id in exact else scores[row.id],
                exact=row.id in exact,
                model=model if row.id in scores else EXACT_MATCH_MODEL,
            )
            for row in candidates
            if row.id in exact or scores.get(row.id, 0.0) >= SIMILAR_THRESHOLD
        ]
        return sorted(found, key=lambda match: (not match.exact, -match.score))

    def __call__(self, question: Question) -> list[SimilarQuestion]:
        """The round hook: :meth:`similar` for an unsaved question, never raising."""
        try:
            return self.similar(
                topic_id=question.topic_id, prompt=question.prompt, content=question.content
            )
        except Exception:
            logger.warning("duplicate check: embedder failed; exact matches only", exc_info=True)
            return self.similar(
                topic_id=question.topic_id,
                prompt=question.prompt,
                content=question.content,
                exact_only=True,
            )


def flag_similar(session: Session, question_id: int, matches: Sequence[SimilarQuestion]) -> None:
    """Write one soft flag per match for ``question_id``. Adds; the caller commits."""
    for match in matches:
        session.add(
            QuestionSimilarityRow(
                question_id=question_id,
                similar_question_id=match.question_id,
                score=match.score,
                model=match.model,
            )
        )


def _normalised(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)
