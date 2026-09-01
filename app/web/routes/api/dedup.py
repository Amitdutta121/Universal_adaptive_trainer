"""Post-generation duplicate flagging for the coverage Generate run (m3).

Lives in the web layer, not :mod:`app.generation` or :mod:`app.coverage`:
``app.generation``'s allowed-dependency list omits ``app.retrieval`` (whose
:class:`~app.retrieval.embedder.Embedder` this needs), and ``app.coverage``
must not import the generator at all. Called from
``run_generation_for_gaps`` in :mod:`app.web.routes.api.coverage`, which
already owns the m2 orchestration for the same reason.

Dedup is a soft flag, never a gate (see MILESTONES.md): a flagged question
still lands in the review queue exactly like any other, with the flag as
extra context.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.persistence.models import QuestionRow, QuestionSimilarityRow
from app.persistence.repositories import QuestionRepository
from app.retrieval.embedder import Embedder

#: A cosine score at or above this is flagged as a possible duplicate. A guess
#: from the near-duplicate literature, uncalibrated -- see MILESTONES.md "m3"
#: and "Deferred" (calibration against the approved/rejected split is future
#: work, not blocking this milestone).
DUPLICATE_THRESHOLD = 0.85


def flag_possible_duplicates(
    session: Session, embedder: Embedder, rows: list[QuestionRow]
) -> int:
    """Flag each of ``rows`` against existing approved/passed questions of the
    same topic, writing a :class:`QuestionSimilarityRow` per pair scoring at
    or above :data:`DUPLICATE_THRESHOLD` and committing.

    Returns how many of ``rows`` received at least one flag -- a question
    count, not a flag-pair count, for the m4 "M possible duplicates" summary.

    Raises on an embedder failure -- the caller is the one with the context to
    decide a flagging failure must never fail the generation run it followed
    (ADR: dedup is a soft flag).
    """
    repo = QuestionRepository(session)
    new_ids = {row.id for row in rows}
    flagged_rows = 0
    for row in rows:
        if row.topic_id is None:
            continue
        candidates = repo.list_dedup_candidates(topic_id=row.topic_id, exclude_ids=new_ids)
        if not candidates:
            continue

        texts = [_embed_text(row)] + [_embed_text(candidate) for candidate in candidates]
        vectors = np.asarray(embedder.embed(texts), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = vectors / norms
        scores = normalized[0] @ normalized[1:].T

        row_flagged = False
        for candidate, score in zip(candidates, scores, strict=True):
            if score >= DUPLICATE_THRESHOLD:
                session.add(
                    QuestionSimilarityRow(
                        question_id=row.id,
                        similar_question_id=candidate.id,
                        score=float(score),
                        model=embedder.model,
                    )
                )
                row_flagged = True
        session.commit()
        if row_flagged:
            flagged_rows += 1
    return flagged_rows


def _embed_text(row: QuestionRow) -> str:
    """``prompt`` plus option text, per MILESTONES.md's m3 spec.

    ``options`` only exists on a multiple-choice question's ``content``; other
    question types embed on ``prompt`` alone.
    """
    content = row.content or {}
    options = content.get("options")
    parts = [row.prompt]
    if isinstance(options, list):
        parts.extend(str(option) for option in options)
    return " ".join(parts)
