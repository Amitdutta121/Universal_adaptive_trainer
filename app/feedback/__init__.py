"""Professor feedback boundary.

Responsibility
    Record professor approve / reject / edit decisions on generated questions
    and expose that history to personalization and generator optimization.

Status
    Review recording, including the Questions UI write path, is implemented and
    backed by :class:`~app.persistence.repositories.ProfessorReviewRepository`.

Key rules
    * Professor feedback is *the* authority for professor preference. Student
      performance never overrides it.
    * Reviews are append-only, and an edit retains the generated original, so
      "what was generated vs. what was accepted" stays recoverable.

Allowed dependencies
    ``app.domain``, ``app.errors``, ``app.persistence``.
    Must not import ``app.generation`` (that direction would create a cycle:
    generation reads preference, preference reads feedback).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.enums import ReviewDecision
from app.errors import DomainRuleError
from app.feedback.service import submit_review
from app.persistence.models import ProfessorReviewRow


def record_review(
    session: Session,
    *,
    question_id: int,
    decision: ReviewDecision,
    comment: str | None = None,
) -> ProfessorReviewRow:
    """Backward-compatible approve helper; new callers should use ``submit_review``."""
    if decision is ReviewDecision.REJECT:
        raise DomainRuleError(
            "record_review no longer supports reject without reasons; use submit_review."
        )
    if decision is ReviewDecision.EDIT:
        raise DomainRuleError("record_review no longer supports edit; use submit_review.")
    return submit_review(
        session,
        question_id=question_id,
        decision=decision,
        comment=comment,
    )
