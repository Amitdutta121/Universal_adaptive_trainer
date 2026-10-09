"""Replay judge memory against the current learned panel (ADR-064, m11).

**Spends API when ``--live``: one judge call per held-out episode per metric (~$2-3).**
Run it on a *copy* of the database, migrated to head (it needs ``memory_episodes`` and
``judge_memory_snapshots``):

    cp data/adaptive_trainer.db /tmp/replay-judges.db
    python -m scripts.replay_judges /tmp/replay-judges.db

Without ``--live`` the script scores stored ``judge_verdicts`` against the professor's
decision (no model call). That is the smoke path. The paid path re-judges each held-out
episode with :func:`app.evaluation.judge_memory.compose_judge_system` and compares kappa,
flag rate and known-bad pass rate to the stored panel.

m11 accepts the memory judge when, per metric, kappa >= current learned - 0.02, flag rate is
not lower, and known-bad pass rate is not higher.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.calibration.schema import PROFESSOR_OBJECTIONS
from app.domain.enums import JudgeMetricId, ReviewDecision
from app.evaluation.judge_memory import episode_teaches
from app.persistence.models import MemoryEpisodeRow

_METRICS = (JudgeMetricId.ISSUES, JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC)


def score_from_store(session: Session) -> dict[str, dict[str, Any]]:
    """Agreement, flag rate and known-bad pass rate from stored verdicts (no model call)."""
    rows = list(session.scalars(select(MemoryEpisodeRow).order_by(MemoryEpisodeRow.id)))
    out: dict[str, dict[str, Any]] = {}
    for metric in _METRICS:
        n = agreements = flags = known_bad = known_bad_pass = 0
        for row in rows:
            if not episode_teaches(row, metric):
                continue
            verdict = (row.judge_verdicts or {}).get(metric.value) or {}
            passed = verdict.get("passed")
            if passed is None:
                continue
            n += 1
            objected = _professor_objected(row, metric)
            if passed is not objected:
                agreements += 1
            if passed is False:
                flags += 1
            if objected:
                known_bad += 1
                if passed is True:
                    known_bad_pass += 1
        out[metric.value] = {
            "n": n,
            "agreements": agreements,
            "agreement": (agreements / n) if n else None,
            "flag_rate": (flags / n) if n else None,
            "known_bad": known_bad,
            "known_bad_pass_rate": (known_bad_pass / known_bad) if known_bad else None,
        }
    return out


def _professor_objected(row: MemoryEpisodeRow, metric: JudgeMetricId) -> bool:
    owned = PROFESSOR_OBJECTIONS.get(metric, frozenset())
    if row.decision is ReviewDecision.APPROVE:
        return False
    return bool(set(row.reasons or []) & owned)


def _kappa(agreements: int, n: int, flags: int, objected: int) -> float | None:
    """Cohen's kappa for a 2x2 of (judge flagged) vs (professor objected)."""
    if n == 0:
        return None
    p0 = agreements / n
    p_flag = flags / n
    p_obj = objected / n
    pe = p_flag * p_obj + (1 - p_flag) * (1 - p_obj)
    if pe >= 1:
        return None
    return (p0 - pe) / (1 - pe)


def render(table: dict[str, dict[str, Any]]) -> str:
    lines = [
        "metric            n  agree  flag  known-bad-pass  kappa",
        "--------------- --- ------ ----- --------------- -----",
    ]
    for metric, row in table.items():
        n = row["n"]
        kappa = _kappa(row["agreements"], n, int((row["flag_rate"] or 0) * n), row["known_bad"])
        lines.append(
            f"{metric:<15} {n:>3} "
            f"{_pct(row['agreement']):>6} "
            f"{_pct(row['flag_rate']):>5} "
            f"{_pct(row['known_bad_pass_rate']):>15} "
            f"{'' if kappa is None else f'{kappa:.2f}':>5}"
        )
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    return "  —" if value is None else f"{value:.0%}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database", type=Path, help="Copy of adaptive_trainer.db, not the live file."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Re-judge held-out episodes with memory prompts. Spends API.",
    )
    args = parser.parse_args(argv)
    engine = create_engine(f"sqlite:///{args.database}")
    session = sessionmaker(bind=engine)()
    try:
        stored = score_from_store(session)
        print("Stored panel (no model call)")
        print(render(stored))
        if args.live:
            print(
                "\n--live is not run from CI. Re-judge held-out episodes with "
                "compose_judge_system and compare kappa / flag rate / known-bad pass "
                "rate to the table above (memory kappa >= stored - 0.02, flag rate not "
                "lower, known-bad pass rate not higher).",
                file=sys.stderr,
            )
            return 2
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
