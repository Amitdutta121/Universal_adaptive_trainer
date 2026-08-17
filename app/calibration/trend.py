"""Agreement panel by panel, in the order the panels ran (ADR-041).

The measurement that can falsify ADR-039. A judge that rewrites itself from its
own mistakes is *assumed* to converge on the professor; nothing so far said
whether it does. This groups the frozen review outcomes by the judge panel that
produced them and reports agreement for each, oldest panel first.

Built from ``review_outcomes`` rather than from the live evaluations, for the
reason the table exists (ADR-037): a bulk re-judge overwrites
``questions.pedagogical_eval``, so a trend computed from live rows would
silently restate history and could show improvement that never happened.

**Faults, not per-metric agreement.** An outcome row records which judges were
*at fault*, not what each judge answered, so the denominator for a per-metric
agreement rate is not recoverable from it. What is recoverable -- and what the
professor actually needs -- is how often each judge was the one that got it
wrong, per panel. That is reported as a count and as a rate over the panel's
outcomes, and it is named ``fault_rate`` rather than dressed up as agreement.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.domain.enums import JudgeMetricId, QuadrantCell
from app.persistence.models import ReviewOutcomeRow
from app.persistence.repositories import ReviewOutcomeRepository

#: Rates are rounded so the JSON is stable across platforms and readable.
_RATE_PLACES = 4

#: Below this many outcomes, a panel's rate says more about which questions
#: happened to be reviewed under it than about the judges. Panels are short-lived
#: while learning is on, so this will often be true and has to be visible.
MIN_PANEL_SAMPLE = 10


class MetricFaults(BaseModel):
    """How often one judge was the one that got it wrong, within one panel."""

    metric: JudgeMetricId
    #: The judge passed a question the professor rejected or rewrote.
    missed: int = 0
    #: The judge failed a question the professor approved.
    false_alarms: int = 0

    @property
    def faults(self) -> int:
        return self.missed + self.false_alarms


class TrendPoint(BaseModel):
    """One judge panel's record, as far as its outcomes go."""

    #: ``None`` for outcomes written before a version was recorded.
    rubric_version: str | None
    n: int
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    confirmed_good: int = 0
    missed: int = 0
    false_alarm: int = 0
    confirmed_bad: int = 0

    #: Agreements over outcomes: the two cells where judge and professor said the
    #: same thing. ``None`` when the panel has no outcomes.
    agreement: float | None = None
    #: Of the questions this panel accepted, the share the professor also kept.
    #: The figure that decides whether auto-acceptance would be safe.
    auto_accept_precision: float | None = None
    #: True while ``n`` is too small for the rates to describe the panel.
    small_sample: bool = True

    metrics: list[MetricFaults] = Field(default_factory=list)

    @property
    def fault_rates(self) -> dict[JudgeMetricId, float | None]:
        """Faults per outcome, per judge. Comparable across panels of any size."""
        return {row.metric: _rate(row.faults, self.n) for row in self.metrics}


class AgreementTrend(BaseModel):
    """Every panel that has produced a measured outcome, oldest first."""

    points: list[TrendPoint] = Field(default_factory=list)
    total: int = 0

    @property
    def improved(self) -> bool | None:
        """Whether the newest panel agrees more often than the oldest.

        ``None`` unless at least two panels have an agreement figure. This is a
        direction, not a result: with panels this small it is one question's
        worth of noise away from flipping, and it deliberately does not claim
        significance.
        """
        rated = [point for point in self.points if point.agreement is not None]
        if len(rated) < 2:
            return None
        return rated[-1].agreement > rated[0].agreement


def build_agreement_trend(session: Session, *, limit: int = 1000) -> AgreementTrend:
    """Group every frozen outcome by its judge panel, oldest panel first."""
    rows = ReviewOutcomeRepository(session).list_recent(limit=limit)
    grouped: dict[str | None, list[ReviewOutcomeRow]] = {}
    for row in rows:
        grouped.setdefault(row.rubric_version, []).append(row)

    points = [_point(version, outcomes) for version, outcomes in grouped.items()]
    # Ordered by when each panel first produced an outcome, so the sequence is
    # the order the judges actually ran rather than alphabetical by fingerprint.
    points.sort(key=lambda point: (point.first_seen is None, point.first_seen))
    return AgreementTrend(points=points, total=len(rows))


def _point(version: str | None, outcomes: list[ReviewOutcomeRow]) -> TrendPoint:
    counts = dict.fromkeys(QuadrantCell, 0)
    for outcome in outcomes:
        counts[outcome.cell] += 1

    total = len(outcomes)
    agreed = counts[QuadrantCell.CONFIRMED_GOOD] + counts[QuadrantCell.CONFIRMED_BAD]
    accepted = counts[QuadrantCell.CONFIRMED_GOOD] + counts[QuadrantCell.MISSED]
    stamps = [outcome.created_at for outcome in outcomes if outcome.created_at is not None]

    return TrendPoint(
        rubric_version=version,
        n=total,
        first_seen=min(stamps) if stamps else None,
        last_seen=max(stamps) if stamps else None,
        confirmed_good=counts[QuadrantCell.CONFIRMED_GOOD],
        missed=counts[QuadrantCell.MISSED],
        false_alarm=counts[QuadrantCell.FALSE_ALARM],
        confirmed_bad=counts[QuadrantCell.CONFIRMED_BAD],
        agreement=_rate(agreed, total),
        auto_accept_precision=_rate(counts[QuadrantCell.CONFIRMED_GOOD], accepted),
        small_sample=total < MIN_PANEL_SAMPLE,
        metrics=_metric_faults(outcomes),
    )


def _metric_faults(outcomes: list[ReviewOutcomeRow]) -> list[MetricFaults]:
    """One row per judge, in enum order, so two panels are comparable."""
    faults = {metric: MetricFaults(metric=metric) for metric in JudgeMetricId}
    for outcome in outcomes:
        for metric in outcome.attributed_metrics or []:
            if outcome.cell is QuadrantCell.MISSED:
                faults[metric].missed += 1
            elif outcome.cell is QuadrantCell.FALSE_ALARM:
                faults[metric].false_alarms += 1
    return list(faults.values())


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, _RATE_PLACES)
