"""Judge verdict schemas, the stored evaluation, and the derived gate."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.enums import Difficulty, JudgeGate, JudgeMetricId, RejectionReason
from app.evaluation.prompts import RUBRIC_VERSION


def _now() -> datetime:
    return datetime.now(UTC)


class IssuesVerdict(BaseModel):
    """What the issues judge returns."""

    issue_codes: list[RejectionReason] = Field(default_factory=list)
    custom_issue: str | None = None
    rationale: str = Field(min_length=1)


class SubtopicVerdict(BaseModel):
    """What the subtopic judge returns: the tags it would assign itself."""

    topic_id: int
    subtopic_ids: list[int] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class DifficultyVerdict(BaseModel):
    """What the difficulty judge returns: the level it would assign itself."""

    difficulty: Difficulty
    rationale: str = Field(min_length=1)


class GeneratabilityVerdict(BaseModel):
    """What the generatability judge returns, about the chunk alone."""

    should_have_generated: bool
    rationale: str = Field(min_length=1)


RESPONSE_MODEL_FOR: dict[JudgeMetricId, type[BaseModel]] = {
    JudgeMetricId.ISSUES: IssuesVerdict,
    JudgeMetricId.SUBTOPIC: SubtopicVerdict,
    JudgeMetricId.DIFFICULTY: DifficultyVerdict,
    JudgeMetricId.GENERATABILITY: GeneratabilityVerdict,
}


class MetricStatus(StrEnum):
    """Whether one judge answered."""

    COMPLETED = "completed"
    ERROR = "error"


class MetricResult(BaseModel):
    """One judge's answer, reduced to a pass flag plus what it actually said.

    ``passed`` is derived, never reported by the judge: three of the four judges
    return a value rather than a verdict, and whether that value counts as a pass
    is decided here by comparing it with what the generator claimed. A judge
    asked to grade itself would be answering a different question.
    """

    metric: JudgeMetricId
    status: MetricStatus = MetricStatus.COMPLETED
    passed: bool | None = None
    rationale: str | None = None
    error_detail: str | None = None

    #: Issues judge.
    issue_codes: list[RejectionReason] = Field(default_factory=list)
    custom_issue: str | None = None
    #: Subtopic judge: the taxonomy it would assign.
    proposed_topic_id: int | None = None
    proposed_subtopic_ids: list[int] = Field(default_factory=list)
    #: Difficulty judge: the level it would assign.
    proposed_difficulty: Difficulty | None = None


class PedagogicalEvalStatus(StrEnum):
    """Whether the judges ran at all, and how completely."""

    COMPLETED = "completed"
    #: At least one judge answered and at least one did not.
    PARTIAL = "partial"
    #: Deterministic validation had already failed, so no judge ran (ADR-024).
    SKIPPED = "skipped"
    #: Every judge failed.
    ERROR = "error"


class PedagogicalEvaluation(BaseModel):
    """Every judge answer for one question, plus the gate derived from them."""

    question_id: int | None = None
    status: PedagogicalEvalStatus
    skip_reason: str | None = None
    #: ``None`` whenever a metric is missing: a gate derived from three answers
    #: would read as a verdict on four.
    gate: JudgeGate | None = None
    metrics: list[MetricResult] = Field(default_factory=list)
    judge_model: str | None = None
    rubric_version: str = RUBRIC_VERSION
    created_at: datetime = Field(default_factory=_now)

    def metric(self, metric: JudgeMetricId) -> MetricResult | None:
        return next((row for row in self.metrics if row.metric is metric), None)

    @property
    def error_details(self) -> list[str]:
        """Professor-facing text for every judge that could not answer."""
        return [
            f"{row.metric.value}: {row.error_detail}"
            for row in self.metrics
            if row.status is MetricStatus.ERROR and row.error_detail
        ]


def derive_gate(metrics: list[MetricResult]) -> JudgeGate | None:
    """Reduce the four metric results to one suggestion, or ``None``.

    All four pass, approve. None of them pass, reject. Anything between needs a
    human. Returning ``None`` when a judge is missing is deliberate: a question
    whose judges partly failed still reaches the professor, and it reaches them
    labelled as unjudged rather than as a verdict resting on partial evidence.
    """
    if len(metrics) < len(JudgeMetricId):
        return None
    verdicts = [row.passed for row in metrics]
    if any(passed is None for passed in verdicts):
        return None
    if all(verdicts):
        return JudgeGate.APPROVED
    if not any(verdicts):
        return JudgeGate.REJECT
    return JudgeGate.NEEDS_REVIEW


def result_from_issues(verdict: IssuesVerdict) -> MetricResult:
    """A question passes the issues metric when the judge named no problem."""
    custom = (verdict.custom_issue or "").strip() or None
    return MetricResult(
        metric=JudgeMetricId.ISSUES,
        passed=not verdict.issue_codes and custom is None,
        rationale=verdict.rationale,
        issue_codes=verdict.issue_codes,
        custom_issue=custom,
    )


def result_from_subtopic(
    verdict: SubtopicVerdict, *, claimed: list[int], topic_id: int
) -> MetricResult:
    """Passes when the judge would assign the same topic and the same subtopics.

    Order is ignored -- the tags are a set, and a judge listing them differently
    has not disagreed about anything.
    """
    return MetricResult(
        metric=JudgeMetricId.SUBTOPIC,
        passed=verdict.topic_id == topic_id and set(verdict.subtopic_ids) == set(claimed),
        rationale=verdict.rationale,
        proposed_topic_id=verdict.topic_id,
        proposed_subtopic_ids=verdict.subtopic_ids,
    )


def result_from_difficulty(verdict: DifficultyVerdict, *, requested: Difficulty) -> MetricResult:
    """Passes when the judge would assign the difficulty that was requested."""
    return MetricResult(
        metric=JudgeMetricId.DIFFICULTY,
        passed=verdict.difficulty is requested,
        rationale=verdict.rationale,
        proposed_difficulty=verdict.difficulty,
    )


def result_from_generatability(verdict: GeneratabilityVerdict) -> MetricResult:
    """Passes when the chunk could support the question that was asked for."""
    return MetricResult(
        metric=JudgeMetricId.GENERATABILITY,
        passed=verdict.should_have_generated,
        rationale=verdict.rationale,
    )


def failed_metric(metric: JudgeMetricId, *, detail: str) -> MetricResult:
    """A judge that could not answer. Not a fail: an absent measurement."""
    return MetricResult(
        metric=metric,
        status=MetricStatus.ERROR,
        passed=None,
        error_detail=detail,
    )


def humanize_judge_error_detail(detail: str | None) -> str:
    """Return a short professor-facing summary of one judge's failure."""
    if not detail or not detail.strip():
        return "This reviewer could not complete its review."
    lowered = detail.lower()
    if "validationerror" in lowered or "validation error" in lowered:
        return "The reviewer returned an incomplete answer."
    if "malformed" in lowered or "usable structured" in lowered:
        return "The reviewer returned a malformed answer."
    if "http" in lowered or "could not reach" in lowered or "provider" in lowered:
        return "The reviewer service was unavailable."
    clean = " ".join(detail.split())
    if len(clean) > 180:
        return clean[:177] + "..."
    return clean


def evaluation_from_metrics(
    metrics: list[MetricResult],
    *,
    question_id: int | None,
    judge_model: str,
) -> PedagogicalEvaluation:
    """Assemble the stored evaluation from whatever the four judges returned."""
    answered = [row for row in metrics if row.status is MetricStatus.COMPLETED]
    if not answered:
        status = PedagogicalEvalStatus.ERROR
    elif len(answered) < len(JudgeMetricId):
        status = PedagogicalEvalStatus.PARTIAL
    else:
        status = PedagogicalEvalStatus.COMPLETED
    return PedagogicalEvaluation(
        question_id=question_id,
        status=status,
        gate=derive_gate(metrics),
        metrics=metrics,
        judge_model=judge_model,
        rubric_version=RUBRIC_VERSION,
    )


def skipped_evaluation(
    *,
    question_id: int | None,
    reason: str = "deterministic_failed",
) -> PedagogicalEvaluation:
    """No judge ran, because deterministic validation had already failed."""
    return PedagogicalEvaluation(
        question_id=question_id,
        status=PedagogicalEvalStatus.SKIPPED,
        skip_reason=reason,
        gate=None,
    )
