"""Coverage boundary: is an approved question set usable for training?

Responsibility
    Answer one question the question bank cannot answer about itself. Every
    question in a set can be good while the set is still unusable, because the
    adaptive engine selects a **subtopic** first and a **difficulty** second
    (see ADR-041). A subtopic with no hard question is a request the
    engine cannot satisfy, however good the questions beside it are.

Status
    Implemented, read-only, and offline. Nothing here generates a question,
    changes a status, or creates a set. It reports a grid and a verdict; the
    professor decides.

Key rules
    * Only **approved** questions count. A question that merely passed
      deterministic validation carries no professor verdict.
    * The grid is walked from the **taxonomy**, not from the questions, so a
      subtopic with nothing at all appears as a row of zeroes rather than
      falling out of a join and reading as covered.
    * A cell needs :data:`MIN_QUESTIONS_PER_CELL`, not one. A served question
      drops to the lowest priority, so a cell holding one question repeats it
      immediately.
    * **Empty** cells block; **thin** cells warn. They are different failures
      and are never merged into one "not ready".

Allowed dependencies
    ``app.domain`` and ``app.persistence`` repositories. Must not import
    ``app.adaptive``, ``app.generation``, ``app.evaluation`` or
    ``app.calibration``.
"""

from __future__ import annotations

from app.coverage.schema import (
    MIN_QUESTIONS_PER_CELL,
    CoverageCell,
    CoverageReport,
    CoverageState,
    SubtopicCoverage,
    TopicCoverage,
    needed_for,
    state_for,
)
from app.coverage.service import build_coverage_report, create_question_set

__all__ = [
    "MIN_QUESTIONS_PER_CELL",
    "CoverageCell",
    "CoverageReport",
    "CoverageState",
    "SubtopicCoverage",
    "TopicCoverage",
    "build_coverage_report",
    "create_question_set",
    "needed_for",
    "state_for",
]
