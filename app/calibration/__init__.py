"""Judge calibration boundary.

Responsibility
    Measure how far the advisory pedagogical judge (ADR-024) can be trusted, by
    comparing verdicts it already made against reviews the professor already
    wrote. Read-only and offline: nothing here generates, evaluates, re-reviews
    or records, so a calibration figure never becomes part of what it measures.

Status
    Implemented for the whole-corpus report. Breakdowns (by difficulty, question
    type, generator or rubric version) and any automation that would act on the
    figures are deliberately absent -- see ``docs/DECISIONS.md`` ADR-029.

Key rules
    * Only ``COMPLETED`` evaluations with a decided advisory band are scored; a
      skipped or errored judge made no prediction to be right or wrong about.
    * The **first** professor review of a question is the one compared, because
      that is the verdict auto-acceptance would have pre-empted.
    * Every rate is ``None`` when its denominator is zero.

Allowed dependencies
    ``app.domain``, ``app.evaluation`` (the judge's stored shape) and
    ``app.persistence`` repositories. Must not import ``app.adaptive``,
    ``app.generation`` or ``app.personalization``.
"""

from __future__ import annotations

from app.calibration.schema import (
    JUDGE_ACCEPT_STATUSES,
    MIN_INFORMATIVE_SAMPLE,
    UNUSABLE_ADVISORY_STATUSES,
    CalibrationLabel,
    CalibrationPair,
    CalibrationReport,
    judge_label,
    professor_label,
)
from app.calibration.service import (
    build_calibration_pairs,
    build_calibration_report,
    metrics_from_pairs,
)

__all__ = [
    "JUDGE_ACCEPT_STATUSES",
    "MIN_INFORMATIVE_SAMPLE",
    "UNUSABLE_ADVISORY_STATUSES",
    "CalibrationLabel",
    "CalibrationPair",
    "CalibrationReport",
    "build_calibration_pairs",
    "build_calibration_report",
    "judge_label",
    "metrics_from_pairs",
    "professor_label",
]
