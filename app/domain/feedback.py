"""Professor feedback entities.

Professor reviews are the authority for professor preference: personalization and
later generator optimization read from these records and never from inferred
signals such as student performance.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RejectionReason, ReviewDecision

REJECTION_REASON_LABELS: dict[RejectionReason, str] = {
    RejectionReason.TECHNICALLY_INCORRECT: "Technically incorrect",
    RejectionReason.INCORRECT_ANSWER: "Incorrect answer",
    RejectionReason.INCORRECT_TESTS: "Incorrect tests",
    RejectionReason.NOT_GROUNDED_IN_SOURCE: "Not grounded in source",
    RejectionReason.WRONG_TOPIC_SUBTOPIC: "Wrong topic/subtopic",
    RejectionReason.TOO_EASY: "Too easy",
    RejectionReason.TOO_DIFFICULT: "Too difficult",
    RejectionReason.AMBIGUOUS: "Ambiguous",
    RejectionReason.POOR_WORDING: "Poor wording",
    RejectionReason.POOR_DISTRACTORS: "Poor distractors",
    RejectionReason.POOR_TESTS: "Poor tests",
    RejectionReason.NOT_PEDAGOGICALLY_USEFUL: "Not pedagogically useful",
    RejectionReason.TOO_SIMILAR_REPETITIVE: "Too similar/repetitive",
    RejectionReason.OTHER: "Other",
}


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
    reasons: list[RejectionReason] = Field(default_factory=list)
    comment: str | None = None
    edited_prompt: str | None = None
    edited_reference_solution: str | None = None
    edited_tests: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    professor_id: int | None = None
    reviewed_generator_name: str | None = None
    reviewed_generator_version: str | None = None
    created_at: datetime = Field(default_factory=_now)
