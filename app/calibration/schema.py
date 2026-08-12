"""Calibration labels, the judge/professor mapping, and the report shape.

The judge and the professor answer the same question in different vocabularies:
the judge produces an advisory band over a rubric, the professor produces an
approve / edit / reject verdict. Comparing them at all requires projecting both
onto one two-valued label, which is what this module defines and what
``docs/DECISIONS.md`` ADR-029 justifies.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from app.domain.enums import ReviewDecision
from app.evaluation import AdvisoryStatus, PedagogicalEvalStatus, PedagogicalEvaluation


class CalibrationLabel(StrEnum):
    """The shared vocabulary both verdicts are projected onto."""

    ACCEPT = "accept"
    NEEDS_REVIEW = "needs_review"


#: The advisory bands that count as the judge saying "ship this unreviewed".
#: Only ``STRONG`` qualifies: auto-acceptance is the decision being measured, so
#: the accept bucket must contain exactly the questions that would actually skip
#: review, not every question the judge merely tolerated.
JUDGE_ACCEPT_STATUSES: frozenset[AdvisoryStatus] = frozenset({AdvisoryStatus.STRONG})

#: Bands that carry no prediction at all. ``SKIPPED`` means the judge never ran
#: (deterministic validation had already failed) and ``ERROR`` means it ran and
#: failed; neither is a wrong answer, so counting either as a prediction would
#: charge the judge for a measurement it never made.
UNUSABLE_ADVISORY_STATUSES: frozenset[AdvisoryStatus] = frozenset(
    {AdvisoryStatus.SKIPPED, AdvisoryStatus.ERROR}
)


def judge_label(evaluation: PedagogicalEvaluation) -> CalibrationLabel | None:
    """Project a stored evaluation onto a label, or ``None`` when unusable.

    ``UNCERTAIN`` is a real prediction, not an absent one: the judge did run and
    declined to vouch for the question, which is exactly what ``NEEDS_REVIEW``
    means to a professor.
    """
    if evaluation.status is not PedagogicalEvalStatus.COMPLETED:
        return None
    if evaluation.overall_advisory_status in UNUSABLE_ADVISORY_STATUSES:
        return None
    if evaluation.overall_advisory_status in JUDGE_ACCEPT_STATUSES:
        return CalibrationLabel.ACCEPT
    return CalibrationLabel.NEEDS_REVIEW


def professor_label(decision: ReviewDecision) -> CalibrationLabel:
    """Project a professor verdict onto a label.

    An ``EDIT`` is a needed correction, so it sits with ``REJECT``: the question
    was not usable as generated, which is what auto-acceptance would have missed.
    """
    if decision is ReviewDecision.APPROVE:
        return CalibrationLabel.ACCEPT
    return CalibrationLabel.NEEDS_REVIEW


#: Below this many pairs, a rate says more about which questions happened to be
#: reviewed than about the judge. Anything reading a calibration figure must be
#: able to say so, so the threshold lives beside the measurement rather than
#: being re-guessed by each client.
MIN_INFORMATIVE_SAMPLE = 20


class CalibrationPair(BaseModel):
    """One question's judge prediction beside the professor's first verdict."""

    question_id: int
    judge: CalibrationLabel
    professor: CalibrationLabel

    @property
    def agrees(self) -> bool:
        """Whether this pair counts toward ``agreement``."""
        return self.judge is self.professor


class CalibrationReport(BaseModel):
    """How well the judge's verdicts matched the professor's.

    Every rate is ``None`` when its denominator is zero. A fresh database has
    nothing to measure, and reporting that as ``0.0`` would read as a judge that
    agrees with nobody rather than as an absent measurement.
    """

    #: Usable pairs, which is the number of questions counted -- not reviews.
    n: int
    #: Denominator of both auto-accept rates, published so a ``None`` or an
    #: extreme rate can be told apart from one resting on a single question.
    judge_accept_count: int
    agreement: float | None
    auto_accept_precision: float | None
    unsafe_auto_accept_rate: float | None
