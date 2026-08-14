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


#: Characters of an edited field quoted as evidence to a rewriter.
EDIT_SNIPPET_CHARS = 240


def professor_edits(
    *,
    changed_fields: list[str],
    edited_prompt: str | None,
    edited_reference_solution: str | None,
    edited_tests: str | None,
    limit: int = EDIT_SNIPPET_CHARS,
) -> dict[str, str]:
    """The fields the professor actually rewrote, and what they became.

    Keyed on ``changed_fields``, which :func:`app.feedback.submit_review` derives
    by comparing the submission with the stored question. An edit form submits
    all three fields whether or not they changed, so quoting ``edited_prompt``
    unconditionally shows a rewriter text identical to the original and hides the
    field that really moved: a professor who fixed only the tests would appear to
    have rewritten the prompt into itself, and the tests would never be
    mentioned.

    Pure, and shared by both rewriters (the generator's and the judges'), because
    the two must read one professor edit the same way.
    """
    values = {
        "prompt": edited_prompt,
        "reference_solution": edited_reference_solution,
        "tests": edited_tests,
    }
    edits = {}
    for field in changed_fields:
        value = (values.get(field) or "").strip()
        if value:
            edits[field] = value[:limit]
    return edits


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
