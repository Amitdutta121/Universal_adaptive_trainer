"""Place one landed review in its quadrant cell, and record it (ADR-037).

This is the per-review half of the loop that :mod:`app.calibration` reports in
bulk. Calibration answers "how has the judge done so far"; this answers "what
just happened, and what does it call for", at the moment the professor presses
submit and while the answer can still be acted on.

Only the free work lives here: cross the judge gate with the professor verdict,
name the judges at fault, and write the dataset row. The paid work -- relearning
a type instruction, which costs a model call -- is triggered by the caller in
:mod:`app.web.routes.api.feedback`, because that is the layer allowed to reach
across subsystems.

A question with no usable judge verdict produces **no row**. Recording it as a
cell would invent a judge opinion where none exists, and the dataset would then
count questions the judge never answered against it.

Allowed dependencies
    ``app.domain``, ``app.persistence``, and the pure label functions of
    ``app.calibration``. Nothing here calls a model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.calibration.schema import (
    PROFESSOR_OBJECTIONS,
    is_held_out,
    judge_label,
    professor_label,
    quadrant_cell,
)
from app.domain.enums import CalibrationLabel, JudgeMetricId, QuadrantCell
from app.evaluation import MetricStatus, PedagogicalEvaluation
from app.persistence.models import ProfessorReviewRow, ReviewOutcomeRow
from app.persistence.repositories import ReviewOutcomeRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewOutcome:
    """Where this review landed, and which judges it implicates."""

    cell: QuadrantCell
    judge: CalibrationLabel
    professor: CalibrationLabel
    #: The judges at fault, empty when none can be attributed.
    attributed_metrics: list[JudgeMetricId]
    held_out: bool
    row: ReviewOutcomeRow

    @property
    def calls_for_instruction_refresh(self) -> bool:
        """The professor did not accept the question, so the generator wrote one
        they would not keep -- whatever the judge thought of it.

        True in ``confirmed_bad`` *and* in ``missed``. The two cells differ in
        whether the judge also erred, which is a fact about the judge; the
        generator's lesson is identical in both, because in both the professor
        rejected or rewrote what it produced. Keying this on the judge's opinion
        would mean a question the judge wrongly approved taught the generator
        nothing, purely because the judge was also wrong about it.
        """
        return self.professor is CalibrationLabel.NEEDS_REVIEW

    @property
    def calls_for_judge_repair(self) -> bool:
        """The two sides disagreed, so a judge is wrong about something."""
        return self.cell in (QuadrantCell.MISSED, QuadrantCell.FALSE_ALARM)


def route_review_outcome(session: Session, review: ProfessorReviewRow) -> ReviewOutcome | None:
    """Record which cell this review fell into. ``None`` when it cannot be placed.

    Not placeable means the question carries no completed judge evaluation: the
    judges were skipped after deterministic validation failed, they all errored,
    or the stored blob predates the current format. In each case there is no
    judge verdict to disagree with.

    Writes at most one row per review; a repeat call is a no-op that returns the
    outcome already stored, so a retried request cannot double-count a question.
    """
    repository = ReviewOutcomeRepository(session)
    existing = repository.get_for_review(review.id)
    if existing is not None:
        return _outcome_from_row(existing)

    question = review.question
    if question is None or question.pedagogical_eval is None:
        return None
    try:
        evaluation = PedagogicalEvaluation.model_validate(question.pedagogical_eval)
    except ValidationError:
        logger.warning(
            "Review %s not placed: question %s carries an evaluation that no longer validates.",
            review.id,
            review.question_id,
        )
        return None

    judge = judge_label(evaluation)
    if judge is None:
        return None

    professor = professor_label(review.decision)
    cell = quadrant_cell(judge, professor)
    attributed = _attributed_metrics(cell, evaluation, set(review.reasons))

    row = repository.add(
        ReviewOutcomeRow(
            review_id=review.id,
            question_id=question.id,
            question_type=question.question_type,
            cell=cell,
            judge=judge,
            professor=professor,
            rubric_version=evaluation.rubric_version,
            judge_model=evaluation.judge_model,
            attributed_metrics=attributed,
            judge_rationales=_rationales_for(evaluation, attributed),
            held_out=is_held_out(question.id),
        )
    )
    logger.info(
        "Review %s on question %s landed in %s (judges at fault: %s).",
        review.id,
        question.id,
        cell.value,
        ", ".join(metric.value for metric in attributed) or "none attributable",
    )
    return _outcome_from_row(row)


def _attributed_metrics(
    cell: QuadrantCell,
    evaluation: PedagogicalEvaluation,
    cited: set,
) -> list[JudgeMetricId]:
    """Name the judges that disagreed with the professor on their own point.

    A judge is at fault in a ``MISSED`` cell when it passed the question and the
    professor cited one of *its* reasons; in a ``FALSE_ALARM`` cell when it
    failed the question and the professor cited none of them. The agreeing cells
    attribute nothing -- there is no fault to place.

    ``GENERATABILITY`` can never appear: the professor's vocabulary has no code
    contradicting it (:data:`PROFESSOR_OBJECTIONS`), so a miss it caused is
    recorded as unattributed rather than blamed on the nearest judge.
    """
    if cell not in (QuadrantCell.MISSED, QuadrantCell.FALSE_ALARM):
        return []
    missed = cell is QuadrantCell.MISSED
    attributed = []
    for metric, reasons in PROFESSOR_OBJECTIONS.items():
        result = evaluation.metric(metric)
        if result is None or result.status is not MetricStatus.COMPLETED or result.passed is None:
            continue
        objected = bool(cited & reasons)
        # A miss blames the judges that passed while the professor objected; a
        # false alarm blames those that failed while the professor did not.
        at_fault = (result.passed and objected) if missed else (not result.passed and not objected)
        if at_fault:
            attributed.append(metric)
    return attributed


def _rationales_for(
    evaluation: PedagogicalEvaluation, attributed: list[JudgeMetricId]
) -> dict[str, str]:
    """What each judge at fault said, kept for the repair that reads it later.

    Only the attributed judges: the others were not contradicted, so their
    reasoning is not evidence about anything and storing it would pad every row
    with text nobody reads.
    """
    rationales = {}
    for metric in attributed:
        result = evaluation.metric(metric)
        if result is not None and result.rationale:
            rationales[metric.value] = result.rationale
    return rationales


def _outcome_from_row(row: ReviewOutcomeRow) -> ReviewOutcome:
    return ReviewOutcome(
        cell=row.cell,
        judge=row.judge,
        professor=row.professor,
        attributed_metrics=list(row.attributed_metrics),
        held_out=row.held_out,
        row=row,
    )
