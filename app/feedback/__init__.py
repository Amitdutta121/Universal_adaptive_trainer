"""Professor feedback boundary.

Responsibility
    Record professor approve / reject / edit decisions on generated questions
    and expose that history to personalization and generator optimization.

Status
    Recording is backed by real storage
    (:class:`~app.persistence.repositories.ProfessorReviewRepository`); writing
    reviews through the UI is deferred with the Questions review screen.

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
from app.persistence.models import ProfessorReviewRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository


def record_review(
    session: Session,
    *,
    question_id: int,
    decision: ReviewDecision,
    comment: str | None = None,
) -> ProfessorReviewRow:
    """Append a professor review for ``question_id``.

    Copies the reviewed question's generator identity onto the review so the
    preference signal survives later changes to the question row.

    Raises:
        NotFoundError: if the question does not exist.
    """
    question = QuestionRepository(session).get(question_id)
    review = ProfessorReviewRow(
        question_id=question.id,
        decision=decision,
        comment=comment,
        reviewed_generator_name=question.generator_name,
        reviewed_generator_version=question.generator_version,
    )
    return ProfessorReviewRepository(session).add(review)
