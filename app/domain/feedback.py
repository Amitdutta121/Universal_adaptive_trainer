"""Professor feedback entities.

Professor reviews are the authority for professor preference: personalization and
later generator optimization read from these records and never from inferred
signals such as student performance.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ReviewDecision


def _now() -> datetime:
    return datetime.now(UTC)


class ProfessorReview(BaseModel):
    """One professor verdict on one generated question.

    Reviews are append-only: a later review of the same question is a new record,
    so the full preference history stays available for generator optimization.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    question_id: int | None = None
    decision: ReviewDecision
    #: Free-text rationale. The most valuable preference signal, so it is kept
    #: verbatim rather than being reduced to tags at write time.
    comment: str | None = None
    #: Which generator produced the reviewed question, copied at review time so
    #: the signal survives regeneration of the question row.
    reviewed_generator_name: str | None = None
    reviewed_generator_version: str | None = None
    created_at: datetime = Field(default_factory=_now)
