"""Per-judge scorecard: agreement with the professor, plus retries and drops from rounds.

Read-only (ADR-064 decision 1). Difficulty and subtopic are scored against the professor's
confirmed values on every review, not only those that cite a disagreement reason. Round
retries and drops are attributed from ``generation_attempts`` by the check name RoundReview
writes; this module does not import ``app.generation``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.calibration.schema import (
    PROFESSOR_OBJECTIONS,
    USABLE_EVAL_STATUSES,
    JudgeScorecard,
    JudgeScorecardReport,
)
from app.domain.enums import Difficulty, JudgeMetricId
from app.domain.questions import GenerationAttempt
from app.evaluation import MetricStatus, PedagogicalEvaluation
from app.persistence.models import ProfessorReviewRow, QuestionRow
from app.persistence.repositories import QuestionRepository

#: The three judges the scorecard measures. Generatability has no professor vocabulary.
SCORECARD_METRICS: tuple[JudgeMetricId, ...] = (
    JudgeMetricId.ISSUES,
    JudgeMetricId.DIFFICULTY,
    JudgeMetricId.SUBTOPIC,
)

#: Check names RoundReview writes onto ``failed_checks``. Kept here so calibration
#: does not import ``app.generation`` (package boundary).
_DIFFICULTY_JUDGE_CHECK = "difficulty_judge"
_TOPIC_JUDGE_CHECK = "topic_judge"
_CHECK_METRIC: dict[str, JudgeMetricId] = {
    _DIFFICULTY_JUDGE_CHECK: JudgeMetricId.DIFFICULTY,
    _TOPIC_JUDGE_CHECK: JudgeMetricId.SUBTOPIC,
}

_RATE_PLACES = 4
#: z for a two-sided 95% Wilson interval.
_Z95 = 1.96


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, _RATE_PLACES)


def wilson_interval(successes: int, n: int, *, z: float = _Z95) -> tuple[float, float] | None:
    """Wilson score interval for a proportion; ``None`` when there is no sample."""
    if n <= 0:
        return None
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denom
    low = round(max(0.0, centre - margin), _RATE_PLACES)
    high = round(min(1.0, centre + margin), _RATE_PLACES)
    return (low, high)


def cohen_kappa(true_neg: int, false_pos: int, false_neg: int, true_pos: int) -> float | None:
    """Cohen's kappa on a 2-by-2: (judge passed, professor kept the requested value).

    ``None`` when there are no observations, or when chance agreement is 1 (κ undefined).
    """
    n = true_neg + false_pos + false_neg + true_pos
    if n == 0:
        return None
    observed = (true_neg + true_pos) / n
    judge_pass = (true_neg + false_neg) / n
    professor_ok = (true_neg + false_pos) / n
    chance = judge_pass * professor_ok + (1.0 - judge_pass) * (1.0 - professor_ok)
    if chance >= 1.0:
        return None
    return round((observed - chance) / (1.0 - chance), _RATE_PLACES)


def score_from_counts(
    metric: JudgeMetricId,
    *,
    n: int,
    agreements: int,
    true_neg: int,
    false_pos: int,
    false_neg: int,
    true_pos: int,
    retries: int = 0,
    drops: int = 0,
) -> JudgeScorecard:
    """Build one row from 2-by-2 counts. ``agreements`` may differ from the diagonal for
    difficulty/subtopic, which score values rather than pass/fail."""
    interval = wilson_interval(agreements, n)
    flags = false_pos + true_pos
    return JudgeScorecard(
        metric=metric,
        n=n,
        agreements=agreements,
        agreement=_rate(agreements, n),
        kappa=cohen_kappa(true_neg, false_pos, false_neg, true_pos),
        agreement_low=None if interval is None else interval[0],
        agreement_high=None if interval is None else interval[1],
        missed=false_neg,
        false_alarms=false_pos,
        flags=flags,
        flag_rate=_rate(flags, n),
        retries=retries,
        drops=drops,
    )


def build_judge_scorecard(
    session: Session, *, course_id: int | None = None
) -> JudgeScorecardReport:
    """Score each judge over the course's reviewed questions and round attempts."""
    questions = QuestionRepository(session).list_reviewed_with_evaluation(course_id=course_id)
    tallies = {metric: _Tally() for metric in SCORECARD_METRICS}
    for row in questions:
        _add_review(tallies, row)

    retries, drops = _round_retries_and_drops(session, course_id=course_id)
    return JudgeScorecardReport(
        judges=[
            score_from_counts(
                metric,
                n=tallies[metric].n,
                agreements=tallies[metric].agreements,
                true_neg=tallies[metric].true_neg,
                false_pos=tallies[metric].false_pos,
                false_neg=tallies[metric].false_neg,
                true_pos=tallies[metric].true_pos,
                retries=retries[metric],
                drops=drops[metric],
            )
            for metric in SCORECARD_METRICS
        ]
    )


class _Tally:
    def __init__(self) -> None:
        self.n = 0
        self.agreements = 0
        self.true_neg = 0
        self.false_pos = 0
        self.false_neg = 0
        self.true_pos = 0


def _chronological_key(review: ProfessorReviewRow) -> tuple[datetime, int]:
    created = review.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (created, review.id)


def _first_review(reviews: list[ProfessorReviewRow]) -> ProfessorReviewRow:
    return min(reviews, key=_chronological_key)


def _add_review(tallies: dict[JudgeMetricId, _Tally], row: QuestionRow) -> None:
    if not row.pedagogical_eval or not row.reviews:
        return
    try:
        evaluation = PedagogicalEvaluation.model_validate(row.pedagogical_eval)
    except ValidationError:
        return
    if evaluation.status not in USABLE_EVAL_STATUSES:
        return
    review = _first_review(list(row.reviews))
    cited = set(review.reasons or [])
    for metric in SCORECARD_METRICS:
        observation = _observation(metric, evaluation, review, row, cited)
        if observation is None:
            continue
        agreed, passed, professor_ok = observation
        tally = tallies[metric]
        tally.n += 1
        tally.agreements += int(agreed)
        if passed and professor_ok:
            tally.true_neg += 1
        elif not passed and professor_ok:
            tally.false_pos += 1
        elif passed and not professor_ok:
            tally.false_neg += 1
        else:
            tally.true_pos += 1


def _observation(
    metric: JudgeMetricId,
    evaluation: PedagogicalEvaluation,
    review: ProfessorReviewRow,
    row: QuestionRow,
    cited: set,
) -> tuple[bool, bool, bool] | None:
    """``(value_agreed, judge_passed, professor_kept_requested)``, or ``None`` if unusable."""
    result = evaluation.metric(metric)
    if result is None or result.status is not MetricStatus.COMPLETED or result.passed is None:
        return None
    passed = bool(result.passed)
    if metric is JudgeMetricId.ISSUES:
        objected = bool(cited & PROFESSOR_OBJECTIONS[JudgeMetricId.ISSUES])
        return (passed is not objected, passed, not objected)

    if metric is JudgeMetricId.DIFFICULTY:
        proposed = _proposed_difficulty(result, row)
        if proposed is None:
            return None
        confirmed = _confirmed_difficulty(review, row)
        requested = _requested_difficulty(row)
        return (proposed is confirmed, passed, confirmed is requested)

    proposed_ids = _proposed_subtopics(result, row)
    if proposed_ids is None:
        return None
    confirmed_ids = _confirmed_subtopics(review, row)
    requested_ids = _requested_subtopics(row)
    return (proposed_ids == confirmed_ids, passed, confirmed_ids == requested_ids)


def _proposed_difficulty(result, row: QuestionRow) -> Difficulty | None:
    if result.proposed_difficulty is not None:
        return Difficulty(result.proposed_difficulty)
    if result.passed:
        return _requested_difficulty(row)
    return None


def _confirmed_difficulty(review: ProfessorReviewRow, row: QuestionRow) -> Difficulty:
    if review.corrected_difficulty is not None:
        return Difficulty(review.corrected_difficulty)
    return Difficulty(row.difficulty)


def _requested_difficulty(row: QuestionRow) -> Difficulty:
    spec = row.spec or {}
    if "difficulty" in spec:
        return Difficulty(spec["difficulty"])
    return Difficulty(row.difficulty)


def _proposed_subtopics(result, row: QuestionRow) -> frozenset[int] | None:
    proposed = set(result.proposed_subtopic_ids or [])
    if proposed:
        return frozenset(proposed)
    if result.passed:
        return _requested_subtopics(row)
    return None


def _confirmed_subtopics(review: ProfessorReviewRow, row: QuestionRow) -> frozenset[int]:
    if review.corrected_subtopic_ids:
        return frozenset(review.corrected_subtopic_ids)
    return frozenset(row.subtopic_ids or [])


def _requested_subtopics(row: QuestionRow) -> frozenset[int]:
    spec = row.spec or {}
    claimed = spec.get("subtopic_ids")
    if claimed:
        return frozenset(claimed)
    return frozenset(row.subtopic_ids or [])


def _round_retries_and_drops(
    session: Session, *, course_id: int | None
) -> tuple[dict[JudgeMetricId, int], dict[JudgeMetricId, int]]:
    retries: dict[JudgeMetricId, int] = defaultdict(int)
    drops: dict[JudgeMetricId, int] = defaultdict(int)
    for row in QuestionRepository(session).list_round_questions(course_id=course_id):
        attempts = list(row.generation_attempts or [])
        if not attempts:
            continue
        for attempt in attempts[:-1]:
            for metric in _judges_on(attempt):
                retries[metric] += 1
        if not attempts[-1].usable:
            for metric in _judges_on(attempts[-1]):
                drops[metric] += 1
    return retries, drops


def _judges_on(attempt: GenerationAttempt) -> set[JudgeMetricId]:
    return {
        _CHECK_METRIC[check.name] for check in attempt.failed_checks if check.name in _CHECK_METRIC
    }
