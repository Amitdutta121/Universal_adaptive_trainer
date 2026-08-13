"""Calibration labels, the judge/professor mapping, and the report shape.

The judge and the professor now answer in one vocabulary: the judge derives an
approve / needs-review / reject gate, the professor records approve / edit /
reject, and both draw their issue codes from the same enum. Comparing them still
projects onto one two-valued label -- what is being measured is whether a
question could safely skip review -- but the per-metric agreement below reads
the two sides directly against each other. ``docs/DECISIONS.md`` ADR-029 and
ADR-031 justify both.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.enums import (
    Difficulty,
    JudgeGate,
    JudgeMetricId,
    RejectionReason,
    ReviewDecision,
)
from app.evaluation import JUDGE_ISSUE_CODES, PedagogicalEvalStatus, PedagogicalEvaluation


class CalibrationLabel(StrEnum):
    """The shared vocabulary both verdicts are projected onto."""

    ACCEPT = "accept"
    NEEDS_REVIEW = "needs_review"


#: Evaluation statuses that carry a prediction at all. ``SKIPPED`` means no judge
#: ran (deterministic validation had already failed), ``ERROR`` means all four
#: failed, and ``PARTIAL`` means the gate could not be derived; none is a wrong
#: answer, so counting any of them would charge the judge for a measurement it
#: never made.
USABLE_EVAL_STATUSES: frozenset[PedagogicalEvalStatus] = frozenset(
    {PedagogicalEvalStatus.COMPLETED}
)


def judge_label(evaluation: PedagogicalEvaluation) -> CalibrationLabel | None:
    """Project a stored evaluation onto a label, or ``None`` when unusable.

    Only ``APPROVED`` counts as accept: auto-acceptance is the decision being
    measured, so the accept bucket must contain exactly the questions that would
    actually skip review. ``REJECT`` sits with ``NEEDS_REVIEW`` because both
    mean the same thing here -- the judge did not vouch for the question.
    """
    if evaluation.status not in USABLE_EVAL_STATUSES or evaluation.gate is None:
        return None
    if evaluation.gate is JudgeGate.APPROVED:
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
    #: Per metric: did that judge pass the question? Absent when it did not
    #: answer, so a failed judge stays out of its own denominator.
    metric_passed: dict[JudgeMetricId, bool] = Field(default_factory=dict)
    #: Per metric: did the professor cite one of its reasons?
    metric_objected: dict[JudgeMetricId, bool] = Field(default_factory=dict)
    #: What the generator claimed and the subtopic judge proposed, when they
    #: differ. ``None`` when they agree or the judge did not answer.
    subtopic_disagreement: tuple[list[int], list[int]] | None = None
    #: The same for difficulty.
    difficulty_disagreement: tuple[Difficulty, Difficulty] | None = None

    @property
    def agrees(self) -> bool:
        """Whether this pair counts toward ``agreement``."""
        return self.judge is self.professor


#: Which professor rejection reasons count as objecting to which metric. A
#: professor who did not cite one of a metric's reasons is read as not objecting
#: to it -- they had the code available and chose not to use it.
#:
#: ``GENERATABILITY`` is absent: the professor's vocabulary has no code for "this
#: source could not support the question that was asked for", so there is nothing
#: on their side to compare that judge against. Inventing a proxy would report an
#: agreement rate for a question the professor was never asked.
PROFESSOR_OBJECTIONS: dict[JudgeMetricId, frozenset[RejectionReason]] = {
    JudgeMetricId.ISSUES: frozenset(JUDGE_ISSUE_CODES),
    JudgeMetricId.SUBTOPIC: frozenset({RejectionReason.WRONG_TOPIC_SUBTOPIC}),
    JudgeMetricId.DIFFICULTY: frozenset({RejectionReason.TOO_EASY, RejectionReason.TOO_DIFFICULT}),
}


class MetricAgreement(BaseModel):
    """How often one judge's answer matched the professor's on the same point."""

    metric: JudgeMetricId
    #: Pairs where this judge answered at all.
    n: int
    #: Of those, how often the judge said the same thing.
    agreement: float | None
    #: The judge passed the metric and the professor objected to it: the cases
    #: auto-acceptance would have let through.
    missed: int
    #: The judge failed the metric and the professor did not object.
    false_alarms: int


class SubtopicConfusion(BaseModel):
    """One pair of disagreeing subtopic claims, and how often it occurred."""

    claimed_subtopic_ids: list[int]
    judge_subtopic_ids: list[int]
    count: int


class DifficultyConfusion(BaseModel):
    """One pair of disagreeing difficulties, and how often it occurred."""

    requested: Difficulty
    judged: Difficulty
    count: int


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
    #: Per-metric agreement, in a fixed order so a report is comparable to the
    #: one before it.
    metrics: list[MetricAgreement] = Field(default_factory=list)
    #: Where the subtopic judge and the generator disagreed, most frequent
    #: first. Read as "the generator claimed X and the judge said Y".
    subtopic_confusions: list[SubtopicConfusion] = Field(default_factory=list)
    #: The same, for requested versus judged difficulty.
    difficulty_confusions: list[DifficultyConfusion] = Field(default_factory=list)
