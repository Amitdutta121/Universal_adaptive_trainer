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

from pydantic import BaseModel, Field

from app.domain.enums import (
    CalibrationLabel,
    Difficulty,
    JudgeGate,
    JudgeMetricId,
    QuadrantCell,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.evaluation import JUDGE_ISSUE_CODES, PedagogicalEvalStatus, PedagogicalEvaluation

#: Re-exported: both enums moved to :mod:`app.domain.enums` when a review outcome
#: became a stored row (ADR-037), because persistence may not import a subsystem.
#: Every reader still names them here, which is where they are documented.
__all__ = [
    "HELD_OUT_DIVISOR",
    "MIN_INFORMATIVE_SAMPLE",
    "PROFESSOR_OBJECTIONS",
    "USABLE_EVAL_STATUSES",
    "CalibrationLabel",
    "CalibrationPair",
    "CalibrationReport",
    "DifficultyConfusion",
    "MetricAgreement",
    "QuadrantCell",
    "QuadrantCounts",
    "SubtopicConfusion",
    "TypeCalibration",
    "is_held_out",
    "judge_label",
    "professor_label",
    "quadrant_cell",
]


def quadrant_cell(judge: CalibrationLabel, professor: CalibrationLabel) -> QuadrantCell:
    """Cross the two labels into one cell."""
    if judge is CalibrationLabel.ACCEPT:
        if professor is CalibrationLabel.ACCEPT:
            return QuadrantCell.CONFIRMED_GOOD
        return QuadrantCell.MISSED
    if professor is CalibrationLabel.ACCEPT:
        return QuadrantCell.FALSE_ALARM
    return QuadrantCell.CONFIRMED_BAD


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

#: One question in this many is held back from judge repair (ADR-035). Three
#: rather than two because the repair list is what the professor reads to find a
#: pattern, and halving it costs more than the check set gains.
HELD_OUT_DIVISOR = 3


def is_held_out(question_id: int) -> bool:
    """Whether this question is reserved for measuring a repaired judge.

    Keyed on the question id because it must not move. A random or
    recency-based split would re-draw itself on every call, so a judge repaired
    against one draw would be scored on a set that had since absorbed the very
    questions it was tuned on.
    """
    return question_id % HELD_OUT_DIVISOR == 0


class CalibrationPair(BaseModel):
    """One question's judge prediction beside the professor's first verdict."""

    question_id: int
    judge: CalibrationLabel
    professor: CalibrationLabel
    #: The type slice this pair belongs to. ``None`` for a question written
    #: before the field existed; such pairs are reported as their own group
    #: rather than folded into a type they never declared.
    question_type: QuestionType | None = None
    #: Which judge produced it. Repairing a judge prompt raises this, so pairs
    #: carrying two values describe two different judges (ADR-034).
    rubric_version: str | None = None
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

    @property
    def cell(self) -> QuadrantCell:
        """Which of the four outcomes this pair is."""
        return quadrant_cell(self.judge, self.professor)

    @property
    def held_out(self) -> bool:
        """Whether this pair is reserved for measuring, not for repairing."""
        return is_held_out(self.question_id)

    @property
    def missed_metrics(self) -> list[JudgeMetricId]:
        """The judges that passed this question while the professor objected.

        The repair list: these are the individual judges behind a ``MISSED``
        pair. ``GENERATABILITY`` can never appear, because the professor's
        vocabulary has no reason to compare it against (see
        :data:`PROFESSOR_OBJECTIONS`) -- an unattributable miss is reported as
        unattributed rather than blamed on the nearest judge.
        """
        return [
            metric
            for metric in PROFESSOR_OBJECTIONS
            if self.metric_passed.get(metric) is True and self.metric_objected.get(metric, False)
        ]

    @property
    def false_alarm_metrics(self) -> list[JudgeMetricId]:
        """The judges that failed this question while the professor did not."""
        return [
            metric
            for metric in PROFESSOR_OBJECTIONS
            if self.metric_passed.get(metric) is False
            and not self.metric_objected.get(metric, False)
        ]


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


class QuadrantCounts(BaseModel):
    """How many pairs fell into each of the four outcomes (ADR-034).

    ``auto_accept_precision`` is ``confirmed_good / (confirmed_good + missed)``:
    the two cells where the judge did *not* accept are absent from it, because
    auto-acceptance would never have released those questions. Publishing all
    four makes that visible, so a professor can see which cell to work on rather
    than inferring it from a rate.
    """

    confirmed_good: int = 0
    missed: int = 0
    false_alarm: int = 0
    confirmed_bad: int = 0


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
    #: The same pairs split four ways rather than two.
    quadrant: QuadrantCounts = Field(default_factory=QuadrantCounts)
    #: Every distinct judge version behind these pairs, sorted. More than one
    #: means the figures describe two judges at once and cannot be read as a
    #: property of the judge running now.
    rubric_versions: list[str] = Field(default_factory=list)
    #: Per-metric agreement, in a fixed order so a report is comparable to the
    #: one before it.
    metrics: list[MetricAgreement] = Field(default_factory=list)
    #: Where the subtopic judge and the generator disagreed, most frequent
    #: first. Read as "the generator claimed X and the judge said Y".
    subtopic_confusions: list[SubtopicConfusion] = Field(default_factory=list)
    #: The same, for requested versus judged difficulty.
    difficulty_confusions: list[DifficultyConfusion] = Field(default_factory=list)


class TypeCalibration(BaseModel):
    """One question type's report, with the pairs that produced it (ADR-034).

    The type is the slice, because the instruction the generator follows is per
    type (ADR-033): a pooled figure describes a mixture of seven generators and
    authorises none of them. The pairs travel with the report so the professor
    can act on the questions rather than on the rate.
    """

    question_type: QuestionType | None
    report: CalibrationReport
    #: The same arithmetic over the held-out pairs alone (ADR-035). This is the
    #: figure a repaired judge is scored on, because ``report`` includes the
    #: questions the repair was allowed to read.
    check_report: CalibrationReport
    pairs: list[CalibrationPair] = Field(default_factory=list)

    def in_cell(self, cell: QuadrantCell) -> list[CalibrationPair]:
        """The pairs in one cell, in the order they were measured."""
        return [pair for pair in self.pairs if pair.cell is cell]

    def to_repair(self, cell: QuadrantCell) -> list[CalibrationPair]:
        """The pairs in one cell that a judge repair may read (ADR-035).

        Held-out pairs are absent. Reading them while rewriting a judge prompt
        is what turns the check set into another tuning set, after which a
        rising agreement figure measures the fitting rather than the judge.
        """
        return [pair for pair in self.in_cell(cell) if not pair.held_out]
