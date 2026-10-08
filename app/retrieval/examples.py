"""What a round target is shown from the bank (ADR-063 point 3).

Two lists per target (one subtopic x difficulty cell, one question type):

* **Examples** -- approved questions to match. The same question type is required (a
  multiple-choice example teaches a code-writing target the wrong shape). Ranked in tiers:
  the exact cell, then the same topic, then the rest; within a tier by cosine to the target
  (:func:`example_query`), or newest first without an embedder. A candidate scoring above
  :data:`EXAMPLE_PAIR_THRESHOLD` against an example already picked is skipped, so two
  near-identical examples never take both slots. Only exact-cell examples speak for the
  level; the prompt labels the others "style only".
* **Already in the bank** -- the questions nearest the target in its cell, approved or
  awaiting review, any type: what the generator must not repeat. Newest first without an
  embedder.

Vectors come from the ``question_embeddings`` cache (:class:`QuestionEmbeddingStore`), so a
target costs one embedding call: the query plus any question not yet cached. An embedder
failure falls back to the no-embedder order; it never costs the round its target.

Replayed on a copy of the dev DB (``scripts/replay_retrieval.py``, 133 approved questions,
each target retrieved from the questions approved before it): the exact-cell lookup alone
found an example for 9.8% of targets; this order finds one for 83.5%, all of the same type.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionStatus, QuestionType
from app.persistence.models import QuestionRow, SubtopicRow
from app.retrieval.duplicates import QuestionEmbeddingStore, embed_text, text_hash
from app.retrieval.embedder import Embedder

logger = logging.getLogger(__name__)

#: Examples shown per target.
MAX_EXAMPLES = 2
#: Existing questions of the cell shown as "already in the bank".
MAX_IN_BANK = 3
#: Above this cosine two examples are near-identical; the second one is skipped.
EXAMPLE_PAIR_THRESHOLD = 0.92
#: Characters of the target's source section in the retrieval query.
QUERY_SECTION_CHARS = 600

#: Approved, or still waiting for the professor (as ``rounds._COUNTED_STATUSES``).
_IN_BANK_STATUSES = (
    QuestionStatus.APPROVED,
    QuestionStatus.GENERATED,
    QuestionStatus.VALIDATION_PASSED,
)


def example_query(
    question_type: QuestionType, difficulty: Difficulty, subtopic_name: str, section_text: str
) -> str:
    """The text a target is embedded as: what is asked for, and the section it comes from."""
    return (
        f"{question_type.value} question, {difficulty.value} difficulty, "
        f"subtopic '{subtopic_name}'. Source: {section_text[:QUERY_SECTION_CHARS]}"
    )


@dataclass(frozen=True)
class BankQuestion:
    """A stored question shown to the generator."""

    question_id: int
    #: Prompt, code and options (:func:`app.retrieval.duplicates.embed_text`).
    text: str
    #: In the target's own subtopic x difficulty cell.
    same_cell: bool


@dataclass(frozen=True)
class TargetExamples:
    examples: list[BankQuestion]
    in_bank: list[BankQuestion]


def retrieve_for_target(
    session: Session,
    embedder: Embedder | None,
    *,
    curriculum_version_id: int,
    question_type: QuestionType,
    subtopic_id: int,
    difficulty: Difficulty,
    section_text: str = "",
    limit: int = MAX_EXAMPLES,
    in_bank_limit: int = MAX_IN_BANK,
    exclude_ids: Collection[int] = (),
) -> TargetExamples:
    """Examples and already-in-the-bank questions for one target. Never raises on the embedder.

    ``exclude_ids`` leaves questions out of both lists (the replay uses it to hide questions
    approved after the target it replays).
    """
    subtopic = session.get(SubtopicRow, subtopic_id)
    stmt = (
        select(QuestionRow)
        .where(
            QuestionRow.curriculum_version_id == curriculum_version_id,
            QuestionRow.status.in_(_IN_BANK_STATUSES),
        )
        .order_by(QuestionRow.created_at.desc(), QuestionRow.id.desc())
    )
    if exclude_ids:
        stmt = stmt.where(QuestionRow.id.not_in(exclude_ids))
    rows = list(session.scalars(stmt))  # newest first: the order without an embedder

    def in_cell(row: QuestionRow) -> bool:
        return row.difficulty == difficulty and (
            subtopic_id in row.subtopic_ids or row.target_subtopic_id == subtopic_id
        )

    candidates = [
        row
        for row in rows
        if row.status == QuestionStatus.APPROVED and row.question_type == question_type
    ]
    cell = [row for row in rows if in_cell(row)]
    pool = list({row.id: row for row in candidates + cell}.values())

    vectors: dict[int, np.ndarray] = {}
    scores: dict[int, float] = {}
    if embedder is not None and pool:
        query_text = example_query(
            question_type, difficulty, subtopic.name if subtopic else "", section_text
        )
        try:
            query, matrix = QuestionEmbeddingStore(session, embedder).embed_with(query_text, pool)
        except Exception:
            logger.warning("example retrieval: embedder failed; newest first", exc_info=True)
        else:
            vectors = {row.id: vector for row, vector in zip(pool, matrix, strict=True)}
            scores = {key: float(vector @ query) for key, vector in vectors.items()}

    topic_id = subtopic.topic_id if subtopic else None

    def tier(row: QuestionRow) -> int:
        if in_cell(row):
            return 0
        return 1 if topic_id is not None and row.topic_id == topic_id else 2

    texts = {row.id: embed_text(row.prompt, row.content) for row in pool}

    def too_close(row: QuestionRow, other: QuestionRow) -> bool:
        if vectors:
            return float(vectors[row.id] @ vectors[other.id]) > EXAMPLE_PAIR_THRESHOLD
        return text_hash(texts[row.id]) == text_hash(texts[other.id])

    # Stable sorts keep newest-first within a tier when there are no scores.
    ranked = sorted(candidates, key=lambda row: (tier(row), -scores.get(row.id, 0.0)))
    picked: list[QuestionRow] = []
    for row in ranked:
        if len(picked) == limit:
            break
        if not any(too_close(row, other) for other in picked):
            picked.append(row)

    shown = {row.id for row in picked}
    nearest = sorted(
        (row for row in cell if row.id not in shown), key=lambda row: -scores.get(row.id, 0.0)
    )[:in_bank_limit]
    return TargetExamples(
        examples=[BankQuestion(row.id, texts[row.id], tier(row) == 0) for row in picked],
        in_bank=[BankQuestion(row.id, texts[row.id], True) for row in nearest],
    )
