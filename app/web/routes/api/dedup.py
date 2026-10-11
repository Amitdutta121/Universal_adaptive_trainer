"""Post-generation duplicate flagging for the coverage Generate run (m3).

Lives in the web layer, not :mod:`app.generation` or :mod:`app.coverage`:
``app.generation``'s allowed-dependency list omits ``app.retrieval`` (whose
:class:`~app.retrieval.embedder.Embedder` this needs), and ``app.coverage``
must not import the generator at all. Called from
``run_generation_for_gaps`` in :mod:`app.web.routes.api.coverage`, which
already owns the m2 orchestration for the same reason.

Dedup is a soft flag, never a gate here (see MILESTONES.md): a flagged question
still lands in the review queue exactly like any other, with the flag as
extra context. The comparison itself, its text and its calibrated thresholds
live in :mod:`app.retrieval.duplicates`, shared with the round retry loop.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.persistence.models import QuestionRow
from app.retrieval.duplicates import DuplicateChecker, flag_similar
from app.retrieval.embedder import Embedder


def flag_possible_duplicates(session: Session, embedder: Embedder, rows: list[QuestionRow]) -> int:
    """Flag each of ``rows`` against existing approved/passed questions of the
    same topic, writing a :class:`QuestionSimilarityRow` per pair scoring at
    or above :data:`~app.retrieval.duplicates.SIMILAR_THRESHOLD` (or matching
    exactly) and committing.

    Returns how many of ``rows`` received at least one flag -- a question
    count, not a flag-pair count, for the m4 "M possible duplicates" summary.

    Raises on an embedder failure -- the caller is the one with the context to
    decide a flagging failure must never fail the generation run it followed
    (ADR: dedup is a soft flag).
    """
    checker = DuplicateChecker(session, embedder)
    new_ids = {row.id for row in rows}
    flagged_rows = 0
    for row in rows:
        matches = checker.similar(
            topic_id=row.topic_id, prompt=row.prompt, content=row.content, exclude_ids=new_ids
        )
        flag_similar(session, row.id, matches)
        session.commit()
        if matches:
            flagged_rows += 1
    return flagged_rows
