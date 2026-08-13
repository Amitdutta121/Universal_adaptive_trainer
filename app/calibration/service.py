"""Pairing stored judge evaluations with professor reviews, and the arithmetic.

Reads only. Nothing here writes a row, calls a model, or changes a question's
status -- a calibration figure is an observation about history, and recording it
would make the next observation partly about itself.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.calibration.schema import (
    PROFESSOR_OBJECTIONS,
    CalibrationLabel,
    CalibrationPair,
    CalibrationReport,
    DifficultyConfusion,
    MetricAgreement,
    SubtopicConfusion,
)
from app.calibration.schema import (
    judge_label as label_for_evaluation,
)
from app.calibration.schema import (
    professor_label as label_for_decision,
)
from app.domain.enums import Difficulty, JudgeMetricId
from app.evaluation import MetricStatus, PedagogicalEvaluation
from app.persistence.models import ProfessorReviewRow, QuestionRow
from app.persistence.repositories import QuestionRepository

logger = logging.getLogger(__name__)

#: Rates are rounded so the JSON is stable across platforms and readable in a
#: report. Four places keep a difference of one question visible well past n=100.
_RATE_PLACES = 4


def _chronological_key(review: ProfessorReviewRow) -> tuple[datetime, int]:
    """Sort key that survives SQLite handing back naive timestamps.

    Reviews written in this session carry the aware ``datetime`` the ORM default
    produced, while reviews read back from SQLite are naive; comparing the two
    raises. The id breaks ties within the same instant, since reviews are
    append-only and ids are issued in the order the professor submitted them.
    """
    created = review.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (created, review.id)


def _first_review(reviews: list[ProfessorReviewRow]) -> ProfessorReviewRow:
    """The professor's *first* verdict on the generated question.

    Not the latest: the judge scored the question as generated, and the first
    review is the verdict on that same artefact. A question edited and then
    approved was not acceptable as generated, so taking the later approval would
    credit the judge for an outcome the professor's own edit produced.
    """
    return min(reviews, key=_chronological_key)


def _pair_for_question(row: QuestionRow) -> CalibrationPair | None:
    """Pair one question, or ``None`` when it cannot be scored."""
    if row.pedagogical_eval is None or not row.reviews:
        return None
    try:
        evaluation = PedagogicalEvaluation.model_validate(row.pedagogical_eval)
    except ValidationError:
        # A blob written by a superseded format tells us nothing about judge
        # accuracy. Skipping keeps it out of both the numerator and the
        # denominator; counting it either way would invent a verdict.
        logger.warning("Skipping question %s: stored evaluation no longer validates", row.id)
        return None

    judge = label_for_evaluation(evaluation)
    if judge is None:
        return None
    review = _first_review(row.reviews)
    cited = set(review.reasons)
    passed = {
        result.metric: result.passed
        for result in evaluation.metrics
        if result.status is MetricStatus.COMPLETED and result.passed is not None
    }
    return CalibrationPair(
        question_id=row.id,
        judge=judge,
        professor=label_for_decision(review.decision),
        metric_passed=passed,
        metric_objected={
            metric: bool(cited & reasons) for metric, reasons in PROFESSOR_OBJECTIONS.items()
        },
        subtopic_disagreement=_subtopic_disagreement(evaluation, row),
        difficulty_disagreement=_difficulty_disagreement(evaluation, row),
    )


def _subtopic_disagreement(
    evaluation: PedagogicalEvaluation, row: QuestionRow
) -> tuple[list[int], list[int]] | None:
    """The claimed and proposed subtopic sets, when the judge proposed others."""
    result = evaluation.metric(JudgeMetricId.SUBTOPIC)
    if result is None or result.passed is not False or not result.proposed_subtopic_ids:
        return None
    return (sorted(row.subtopic_ids), sorted(result.proposed_subtopic_ids))


def _difficulty_disagreement(
    evaluation: PedagogicalEvaluation, row: QuestionRow
) -> tuple[Difficulty, Difficulty] | None:
    """The requested and proposed difficulty, when the judge proposed another."""
    result = evaluation.metric(JudgeMetricId.DIFFICULTY)
    if result is None or result.passed is not False or result.proposed_difficulty is None:
        return None
    return (Difficulty(row.difficulty), result.proposed_difficulty)


def build_calibration_pairs(session: Session) -> list[CalibrationPair]:
    """Every reviewed question the judge actually rendered a verdict on."""
    rows = QuestionRepository(session).list_reviewed_with_evaluation()
    pairs = [_pair_for_question(row) for row in rows]
    return [pair for pair in pairs if pair is not None]


def metrics_from_pairs(pairs: list[CalibrationPair]) -> CalibrationReport:
    """Compute the report from pairs alone, with no database involved."""
    total = len(pairs)
    accepted = [pair for pair in pairs if pair.judge is CalibrationLabel.ACCEPT]
    matching = sum(1 for pair in pairs if pair.judge is pair.professor)
    confirmed = sum(1 for pair in accepted if pair.professor is CalibrationLabel.ACCEPT)

    return CalibrationReport(
        n=total,
        judge_accept_count=len(accepted),
        agreement=_rate(matching, total),
        auto_accept_precision=_rate(confirmed, len(accepted)),
        # Exactly ``1 - auto_accept_precision`` while there are two professor
        # labels; reported separately because it is the figure that decides
        # whether auto-acceptance is safe to turn on.
        unsafe_auto_accept_rate=_rate(len(accepted) - confirmed, len(accepted)),
        metrics=[_metric_agreement(metric, pairs) for metric in PROFESSOR_OBJECTIONS],
        subtopic_confusions=_subtopic_confusions(pairs),
        difficulty_confusions=_difficulty_confusions(pairs),
    )


def _metric_agreement(metric: JudgeMetricId, pairs: list[CalibrationPair]) -> MetricAgreement:
    """Agreement for one metric over the pairs whose judge answered it."""
    answered = [pair for pair in pairs if metric in pair.metric_passed]
    matching = 0
    missed = 0
    false_alarms = 0
    for pair in answered:
        passed = pair.metric_passed[metric]
        objected = pair.metric_objected.get(metric, False)
        if passed is not objected:
            matching += 1
        elif passed:
            missed += 1
        else:
            false_alarms += 1
    return MetricAgreement(
        metric=metric,
        n=len(answered),
        agreement=_rate(matching, len(answered)),
        missed=missed,
        false_alarms=false_alarms,
    )


def _subtopic_confusions(pairs: list[CalibrationPair]) -> list[SubtopicConfusion]:
    """Every claimed/proposed subtopic mismatch, most frequent first."""
    counts: dict[tuple[tuple[int, ...], tuple[int, ...]], int] = {}
    for pair in pairs:
        if pair.subtopic_disagreement is None:
            continue
        claimed, judged = pair.subtopic_disagreement
        key = (tuple(claimed), tuple(judged))
        counts[key] = counts.get(key, 0) + 1
    return [
        SubtopicConfusion(
            claimed_subtopic_ids=list(claimed),
            judge_subtopic_ids=list(judged),
            count=count,
        )
        for (claimed, judged), count in sorted(counts.items(), key=lambda item: -item[1])
    ]


def _difficulty_confusions(pairs: list[CalibrationPair]) -> list[DifficultyConfusion]:
    """Every requested/judged difficulty mismatch, most frequent first."""
    counts: dict[tuple[Difficulty, Difficulty], int] = {}
    for pair in pairs:
        if pair.difficulty_disagreement is None:
            continue
        counts[pair.difficulty_disagreement] = counts.get(pair.difficulty_disagreement, 0) + 1
    return [
        DifficultyConfusion(requested=requested, judged=judged, count=count)
        for (requested, judged), count in sorted(counts.items(), key=lambda item: -item[1])
    ]


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, _RATE_PLACES)


def build_calibration_report(session: Session) -> CalibrationReport:
    """The judge reliability report over all reviewed, evaluated questions."""
    return metrics_from_pairs(build_calibration_pairs(session))
