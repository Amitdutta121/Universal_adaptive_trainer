"""Calibrate the duplicate thresholds against professor verdicts (ADR-063 point 6).

**Spends API: one embedding call per ~32 questions of the DB (cents).** Run it on a *copy* of
the database, never the live file -- it only reads, but the copy keeps a slow run from holding
the live file open:

    cp data/adaptive_trainer.db /tmp/dedup.db
    python -m scripts.calibrate_dedup /tmp/dedup.db
    python -m scripts.calibrate_dedup /tmp/dedup.db --no-code   # the pre-ADR-063 text

For every reviewed question q, its score is the max cosine of q's compare text
(:func:`app.retrieval.duplicates.embed_text`: prompt + code + options) to any question created
before q, in the same topic (what the round check compares) and in the same taxonomy version.
Groups by q's first review: DUP = rejected as ``too_similar_repetitive``, APPROVED = approved or
edited, OTHER_REJECT = rejected for anything else. The table shows, per threshold, how many
DUP rejects it catches and how many approvals it would also hit; the constants in
:mod:`app.retrieval.duplicates` record the run they were chosen from.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import create_engine, text

from app.domain.enums import RejectionReason, ReviewDecision
from app.retrieval.duplicates import embed_text
from app.retrieval.embedder import Embedder

THRESHOLDS = (0.75, 0.80, 0.85, 0.90, 0.95)

_QUESTIONS = """
SELECT q.id, q.curriculum_version_id AS version, q.topic_id AS topic,
       q.question_type AS type, q.prompt, q.content_json, q.created_at AS made,
       (SELECT decision FROM professor_reviews r WHERE r.question_id = q.id
        ORDER BY r.created_at LIMIT 1) AS decision,
       (SELECT reasons_json FROM professor_reviews r WHERE r.question_id = q.id
        ORDER BY r.created_at LIMIT 1) AS reasons
FROM questions q ORDER BY q.created_at, q.id
"""


def load_questions(db_path: Path) -> list[dict[str, Any]]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(_QUESTIONS)).mappings()]
    finally:
        engine.dispose()


def compare_text(question: dict[str, Any], *, with_code: bool) -> str:
    content = json.loads(question["content_json"] or "{}")
    if not with_code:
        content.pop("code", None)
    return embed_text(question["prompt"], content)


def group(question: dict[str, Any]) -> str | None:
    decision = question["decision"]
    if decision is None:
        return None
    if decision in (ReviewDecision.APPROVE.value, ReviewDecision.EDIT.value):
        return "APPROVED"
    if RejectionReason.TOO_SIMILAR_REPETITIVE.value in (question["reasons"] or ""):
        return "DUP"
    return "OTHER_REJECT"


def _auc(positives: list[float], negatives: list[float]) -> float:
    if not positives or not negatives:
        return float("nan")
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in positives for n in negatives]))


def calibrate(
    questions: Sequence[dict[str, Any]], embedder: Embedder, *, with_code: bool = True
) -> str:
    """The report: per scope, group medians, AUC and the threshold table."""
    if not questions:
        return "No questions in this database."
    vectors = np.asarray(
        embedder.embed([compare_text(q, with_code=with_code) for q in questions]),
        dtype=np.float32,
    )
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vectors /= norms

    scores: dict[str, dict[str, list[float]]] = {"topic": {}, "version": {}}
    by_type: dict[tuple[str, str], list[float]] = {}
    for i, question in enumerate(questions):
        label = group(question)
        if label is None:
            continue
        for scope in scores:
            pool = [
                j
                for j in range(i)
                if questions[j]["version"] == question["version"]
                and questions[j]["made"] < question["made"]
                and (scope == "version" or questions[j]["topic"] == question["topic"])
            ]
            if not pool:
                continue
            best = float(np.max(vectors[pool] @ vectors[i]))
            scores[scope].setdefault(label, []).append(best)
            if scope == "topic":
                by_type.setdefault((str(question["type"]), label), []).append(best)

    lines = [f"compare text: prompt{' + code' if with_code else ''} + options"]
    for scope, groups in scores.items():
        lines.append(f"\n== scope: same {scope} ==")
        for label, values in sorted(groups.items()):
            lines.append(
                f"  {label:13s} n={len(values):3d}  median={np.median(values):.3f}"
                f"  p25={np.percentile(values, 25):.3f}  p75={np.percentile(values, 75):.3f}"
            )
        dup, approved = groups.get("DUP", []), groups.get("APPROVED", [])
        other = groups.get("OTHER_REJECT", [])
        lines.append(f"  AUC(DUP vs APPROVED) = {_auc(dup, approved):.3f}")
        lines.append("  thr   catches_DUP   flags_APPROVED   flags_OTHER_REJECT")
        for threshold in THRESHOLDS:

            def hit(values: list[float], t: float = threshold) -> str:
                return f"{sum(v >= t for v in values)}/{len(values)}"

            lines.append(
                f"  {threshold:.2f}  {hit(dup):>10s}   {hit(approved):>13s}   {hit(other):>12s}"
            )

    lines.append("\nper type (same topic): median max-cos, count >= 0.90")
    for (kind, label), values in sorted(by_type.items()):
        lines.append(
            f"  {kind:18s} {label:13s} n={len(values):3d} median={np.median(values):.3f}"
            f"  >=0.90: {sum(v >= 0.90 for v in values)}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("db", type=Path, help="Path to a COPY of the SQLite database.")
    parser.add_argument(
        "--no-code", action="store_true", help="Compare on prompt + options only (old text)."
    )
    args = parser.parse_args(argv)
    if not args.db.is_file():
        parser.error(f"no such database file: {args.db}")

    # Imported here so --help and a bad path cost nothing and read no settings.
    from app.config import get_settings
    from app.retrieval import get_embedder

    embedder = get_embedder(get_settings())
    print(calibrate(load_questions(args.db), embedder, with_code=not args.no_code))
    return 0


if __name__ == "__main__":
    sys.exit(main())
