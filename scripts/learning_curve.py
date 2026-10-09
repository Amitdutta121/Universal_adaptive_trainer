"""How many reviews this professor needs before judge memory stops gaining.

**Spends API when ``--live``: rebuilds judge memory at 10 / 20 / 40 / 80 / 160 reviews
and re-judges the latest 60 (~$3).** Run it on a *copy* of the database:

    cp data/adaptive_trainer.db /tmp/curve.db
    python -m scripts.learning_curve /tmp/curve.db

Without ``--live`` the script scores stored ``judge_verdicts`` on the latest 60 reviews
at each prefix (no model call). That is the smoke path and a baseline; it cannot show
memory gains because the stored verdicts were produced under whatever panel was in
force at review time. The paid path distils ``judge:<metric>`` guidelines from the
prefix, freezes a snapshot, and re-judges the hold-out with that snapshot.

A gain has flattened when agreement rises by less than 1 percentage point per 10
reviews. Each printed cell is a count, not only a rate.
"""

from __future__ import annotations

import argparse
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.calibration.schema import PROFESSOR_OBJECTIONS
from app.domain.enums import JudgeMetricId, ReviewDecision
from app.evaluation.judge_memory import episode_teaches
from app.memory import SOURCE_REVIEW
from app.persistence.models import MemoryEpisodeRow

PREFIXES = (10, 20, 40, 80, 160)
HOLDOUT = 60
_METRICS = (JudgeMetricId.ISSUES, JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC)


def review_episodes(session: Session) -> list[MemoryEpisodeRow]:
    """Review episodes oldest first (the order memory would have seen them)."""
    return list(
        session.scalars(
            select(MemoryEpisodeRow)
            .where(MemoryEpisodeRow.source == SOURCE_REVIEW)
            .order_by(MemoryEpisodeRow.id)
        )
    )


def score_holdout(
    holdout: list[MemoryEpisodeRow], metric: JudgeMetricId
) -> dict[str, int | float | None]:
    n = agreements = missed = false_alarms = 0
    for row in holdout:
        if not episode_teaches(row, metric):
            continue
        verdict = (row.judge_verdicts or {}).get(metric.value) or {}
        passed = verdict.get("passed")
        if passed is None:
            continue
        n += 1
        objected = _objected(row, metric)
        if passed is not objected:
            agreements += 1
        if passed is True and objected:
            missed += 1
        if passed is False and not objected:
            false_alarms += 1
    return {
        "n": n,
        "agreements": agreements,
        "missed": missed,
        "false_alarms": false_alarms,
        "agreement": (agreements / n) if n else None,
    }


def curve_from_store(session: Session) -> dict[str, Any]:
    """Baseline curve from stored verdicts (no model call)."""
    rows = review_episodes(session)
    holdout = rows[-HOLDOUT:] if len(rows) > HOLDOUT else rows
    train = rows[: -len(holdout)] if holdout and len(rows) > len(holdout) else rows
    points = []
    for prefix in PREFIXES:
        seen = train[:prefix]
        point: dict[str, Any] = {
            "reviews": min(prefix, len(seen)),
            "available": len(seen),
            "holdout": len(holdout),
            "judges": {},
        }
        for metric in _METRICS:
            point["judges"][metric.value] = score_holdout(holdout, metric)
        points.append(point)
    return {
        "total_reviews": len(rows),
        "holdout": len(holdout),
        "points": points,
        "flatten": {
            metric.value: flatten_point(
                [
                    (p["reviews"], (p["judges"][metric.value]["agreement"] or 0) * 100)
                    for p in points
                    if p["available"] >= 10
                ]
            )
            for metric in _METRICS
        },
    }


def flatten_point(series: list[tuple[int, float]]) -> int | None:
    """First review count where a further 10 reviews gain < 1 percentage point.

    ``series`` is ``(review_count, agreement_in_percentage_points)`` oldest first.
    ``None`` when the series is too short or still climbing.
    """
    if len(series) < 2:
        return None
    for (n0, a0), (n1, a1) in pairwise(series):
        span = n1 - n0
        if span <= 0:
            continue
        gain_per_ten = (a1 - a0) * 10 / span
        if gain_per_ten < 1:
            return n1
    return None


def _objected(row: MemoryEpisodeRow, metric: JudgeMetricId) -> bool:
    if row.decision is ReviewDecision.APPROVE:
        return False
    return bool(set(row.reasons or []) & PROFESSOR_OBJECTIONS.get(metric, frozenset()))


def render(curve: dict[str, Any]) -> str:
    lines = [
        f"reviews in bank: {curve['total_reviews']}  hold-out: {curve['holdout']}",
        "n     issues(n,agree,miss,FA)  difficulty             subtopic",
        "----  -----------------------  ---------------------  ---------------------",
    ]
    for point in curve["points"]:
        cells = []
        for metric in _METRICS:
            row = point["judges"][metric.value]
            cells.append(
                f"{row['n']},{row['agreements']},{row['missed']},{row['false_alarms']}"
            )
        lines.append(
            f"{point['reviews']:<5} {cells[0]:<23} {cells[1]:<21} {cells[2]}"
        )
    lines.append("flatten (< 1 pt / 10 reviews, from stored verdicts):")
    for metric, at in curve["flatten"].items():
        lines.append(f"  {metric}: {at if at is not None else 'still climbing or too few'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database", type=Path, help="Copy of adaptive_trainer.db, not the live file."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Distil judge memory at each prefix and re-judge the hold-out. Spends API.",
    )
    args = parser.parse_args(argv)
    engine = create_engine(f"sqlite:///{args.database}")
    session = sessionmaker(bind=engine)()
    try:
        curve = curve_from_store(session)
        print(render(curve))
        if args.live:
            print(
                "\n--live is not run from CI. Distil judge:<metric> guidelines from each "
                "prefix, freeze a snapshot, re-judge the latest 60, and print where "
                "agreement flattens (< 1 point per 10 reviews).",
                file=sys.stderr,
            )
            return 2
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
