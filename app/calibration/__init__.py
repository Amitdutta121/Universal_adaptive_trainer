"""Judge calibration boundary.

Responsibility
    Measure how far the advisory pedagogical judge (ADR-024) can be trusted, by
    comparing verdicts it already made against reviews the professor already
    wrote. Read-only and offline: nothing here generates, evaluates, re-reviews
    or records, so a calibration figure never becomes part of what it measures.

Status
    Implemented for the whole-corpus report, for the four-cell split of it, and
    for the per-question-type breakdown (ADR-034). Breakdowns by difficulty or
    generator, and any automation that would act on the figures, are still
    deliberately absent -- see ``docs/DECISIONS.md`` ADR-029.

Key rules
    * Only ``COMPLETED`` evaluations carrying a derived gate are scored; a
      skipped, partial or errored judgement made no prediction to be right or
      wrong about.
    * The **first** professor review of a question is the one compared, because
      that is the verdict auto-acceptance would have pre-empted.
    * Per-metric agreement reads a professor who did not cite a metric's reason
      as not objecting to it (ADR-031).
    * Every rate is ``None`` when its denominator is zero.
    * Of the four cells, only ``MISSED`` makes auto-acceptance unsafe;
      ``FALSE_ALARM`` costs coverage and nothing else.
    * A fault is attributed to a named judge only where the professor's
      vocabulary can contradict it, so ``GENERATABILITY`` is never blamed.
    * One question in :data:`HELD_OUT_DIVISOR` is kept out of the repair lists
      and scores the repaired judge instead (ADR-035). The split is keyed on
      the question id so it cannot re-draw itself between two measurements.

Allowed dependencies
    ``app.domain``, ``app.evaluation`` (the judge's stored shape) and
    ``app.persistence`` repositories. Must not import ``app.adaptive``,
    ``app.generation`` or ``app.personalization``.
"""

from __future__ import annotations

from app.calibration.schema import (
    HELD_OUT_DIVISOR,
    MIN_INFORMATIVE_SAMPLE,
    PROFESSOR_OBJECTIONS,
    USABLE_EVAL_STATUSES,
    CalibrationLabel,
    CalibrationPair,
    CalibrationReport,
    DifficultyConfusion,
    MetricAgreement,
    QuadrantCell,
    QuadrantCounts,
    SubtopicConfusion,
    TypeCalibration,
    is_held_out,
    judge_label,
    professor_label,
    quadrant_cell,
)
from app.calibration.service import (
    build_calibration_pairs,
    build_calibration_report,
    build_type_calibrations,
    for_repair,
    held_out,
    metrics_from_pairs,
    reports_by_type,
)
from app.calibration.trend import (
    MIN_PANEL_SAMPLE,
    AgreementTrend,
    MetricFaults,
    TrendPoint,
    build_agreement_trend,
)

__all__ = [
    "HELD_OUT_DIVISOR",
    "MIN_INFORMATIVE_SAMPLE",
    "MIN_PANEL_SAMPLE",
    "PROFESSOR_OBJECTIONS",
    "USABLE_EVAL_STATUSES",
    "AgreementTrend",
    "CalibrationLabel",
    "CalibrationPair",
    "CalibrationReport",
    "DifficultyConfusion",
    "MetricAgreement",
    "MetricFaults",
    "QuadrantCell",
    "QuadrantCounts",
    "SubtopicConfusion",
    "TrendPoint",
    "TypeCalibration",
    "build_agreement_trend",
    "build_calibration_pairs",
    "build_calibration_report",
    "build_type_calibrations",
    "for_repair",
    "held_out",
    "is_held_out",
    "judge_label",
    "metrics_from_pairs",
    "professor_label",
    "quadrant_cell",
    "reports_by_type",
]
