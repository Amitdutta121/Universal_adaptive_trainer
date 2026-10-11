"""Replay round example retrieval on the real bank (ADR-063 point 3, m3).

**Spends API: one embedding call per approved question, plus one for the bank (cents).**
Run it on a *copy* of the database, migrated to head (it needs ``question_embeddings`` and
``memory_episodes``, where examples are read from); it
writes the copy's embedding cache, so a second run costs only the per-target queries:

    cp data/adaptive_trainer.db /tmp/replay.db
    python -m scripts.replay_retrieval /tmp/replay.db

For every professor-approved question q, in approval order, its target (taxonomy version,
subtopic, difficulty, type, source section) is retrieved for as if it were about to be
generated, with only the questions approved before q was created in the bank. Two methods:

* ``DB``: the pre-m3 lookup -- the two newest approved questions of the same subtopic and
  difficulty, of any type.
* ``REC``: :func:`app.retrieval.examples.retrieve_for_target`, the implemented method.

Per method: coverage (targets given at least one example), the share of examples of the same
type and of the same subtopic, the mean cosine of an example to q (the question the professor
accepted for that target), and near-duplicates (an example above 0.92 to q). m3 accepts REC at
coverage >= 80% and same type 100%.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Collection
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from app.domain.enums import QuestionStatus, ReviewDecision
from app.persistence.models import BookSectionRow, ProfessorReviewRow, QuestionRow
from app.retrieval.duplicates import QuestionEmbeddingStore
from app.retrieval.embedder import Embedder
from app.retrieval.examples import EXAMPLE_PAIR_THRESHOLD, MAX_EXAMPLES, retrieve_for_target
from app.subjects import profile_for_version

METHODS = ("DB", "REC")


def approved_in_order(session: Session) -> list[tuple[QuestionRow, datetime]]:
    """Approved questions with the time of their first approve/edit review, oldest first."""
    approved_at = func.min(ProfessorReviewRow.created_at)
    stmt = (
        select(QuestionRow, approved_at)
        .join(ProfessorReviewRow, ProfessorReviewRow.question_id == QuestionRow.id)
        .where(
            QuestionRow.status == QuestionStatus.APPROVED,
            ProfessorReviewRow.decision.in_((ReviewDecision.APPROVE, ReviewDecision.EDIT)),
        )
        .group_by(QuestionRow.id)
        .order_by(approved_at, QuestionRow.id)
    )
    return [(row, _naive(at)) for row, at in session.execute(stmt)]


def _naive(stamp: datetime) -> datetime:
    """UTC without tzinfo: SQLite returns stored stamps naive, fresh rows carry UTC."""
    return stamp.replace(tzinfo=None)


def _subtopic(row: QuestionRow) -> int | None:
    if row.target_subtopic_id is not None:
        return row.target_subtopic_id
    return row.subtopic_ids[0] if row.subtopic_ids else None


def _section_text(session: Session, row: QuestionRow) -> str:
    sources = (row.content or {}).get("sources") or [{}]
    section_id = sources[0].get("section_id")
    section = session.get(BookSectionRow, section_id) if section_id is not None else None
    return section.text if section is not None else ""


def _db_examples(
    target: QuestionRow, subtopic_id: int, pool: Collection[QuestionRow]
) -> list[QuestionRow]:
    """The pre-m3 ``accepted_examples``: newest of the same subtopic and difficulty, any type."""
    cell = [
        row
        for row in pool
        if row.difficulty == target.difficulty and subtopic_id in row.subtopic_ids
    ]
    cell.sort(key=lambda row: (row.created_at, row.id), reverse=True)
    return cell[:MAX_EXAMPLES]


def replay(session: Session, embedder: Embedder) -> dict[str, dict[str, Any]]:
    """The per-method report. Writes the embedding cache (flushed, not committed)."""
    approved = approved_in_order(session)
    every_approved = set(
        session.scalars(select(QuestionRow.id).where(QuestionRow.status == QuestionStatus.APPROVED))
    )
    if not approved:
        return {}
    # One call fills the cache; every vector below is read from it.
    _, matrix = QuestionEmbeddingStore(session, embedder).embed_with(
        "warm-up", [row for row, _ in approved]
    )
    vectors = {row.id: vector for (row, _), vector in zip(approved, matrix, strict=True)}
    by_id = {row.id: row for row, _ in approved}

    stats = {
        method: {
            "targets": 0,
            "covered": 0,
            "shown": 0,
            "same_type": 0,
            "same_subtopic": 0,
            "cosines": [],
            "near_duplicates": 0,
        }
        for method in METHODS
    }
    for target, _ in approved:
        subtopic_id = _subtopic(target)
        if target.question_type is None or subtopic_id is None:
            continue
        pool = [
            row
            for row, at in approved
            if at < _naive(target.created_at)
            and row.id != target.id
            and row.curriculum_version_id == target.curriculum_version_id
        ]
        if not pool:
            continue
        found = retrieve_for_target(
            session,
            embedder,
            curriculum_version_id=target.curriculum_version_id,
            subject=profile_for_version(session, target.curriculum_version_id).personal_key,
            question_type=target.question_type,
            subtopic_id=subtopic_id,
            difficulty=target.difficulty,
            section_text=_section_text(session, target),
            exclude_ids=every_approved - {row.id for row in pool},
        )
        picks = {
            "DB": _db_examples(target, subtopic_id, pool),
            "REC": [by_id[ex.question_id] for ex in found.examples if ex.question_id in by_id],
        }
        for method, picked in picks.items():
            entry = stats[method]
            entry["targets"] += 1
            entry["covered"] += bool(picked)
            for row in picked:
                cosine = float(vectors[row.id] @ vectors[target.id])
                entry["shown"] += 1
                entry["same_type"] += row.question_type == target.question_type
                entry["same_subtopic"] += subtopic_id in row.subtopic_ids
                entry["cosines"].append(cosine)
                entry["near_duplicates"] += cosine > EXAMPLE_PAIR_THRESHOLD

    report: dict[str, dict[str, Any]] = {}
    for method, entry in stats.items():
        shown = max(entry["shown"], 1)
        report[method] = {
            "targets": entry["targets"],
            "coverage": round(entry["covered"] / max(entry["targets"], 1), 3),
            "examples_shown": entry["shown"],
            "same_type": round(entry["same_type"] / shown, 3),
            "same_subtopic": round(entry["same_subtopic"] / shown, 3),
            "mean_cos_to_accepted": (
                round(float(np.mean(entry["cosines"])), 3) if entry["cosines"] else None
            ),
            "near_duplicates": entry["near_duplicates"],
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("db", type=Path, help="Path to a COPY of the SQLite database.")
    args = parser.parse_args(argv)
    if not args.db.is_file():
        parser.error(f"no such database file: {args.db}")
    engine = create_engine(f"sqlite:///{args.db.as_posix()}")
    if not inspect(engine).has_table("question_embeddings"):
        parser.error("the copy predates migration 0014; upgrade it to head first")

    # Imported here so --help and a bad path cost nothing and read no settings.
    from app.config import get_settings
    from app.retrieval import get_embedder

    embedder = get_embedder(get_settings())
    try:
        with Session(engine) as session:
            print(json.dumps(replay(session, embedder), indent=1))
            session.commit()  # keep the copy's embedding cache for the next run
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
