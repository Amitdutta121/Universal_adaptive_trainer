"""Which reviews are evidence for one question type of one subject (ADR-033, ADR-059).

What the generator is told is no longer learned here. The rewritten rule list this module
kept (``type_instructions``) was replaced by guidelines edited through operations, behind a
two-review threshold and an output-contract filter (ADR-063, :mod:`app.memory.guidelines`):
a single adversarial comment had become a rule every later question obeyed. What stays is
the evidence count the instructions API shows per type.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.assessment.catalog import LEGACY_SUBJECT
from app.domain.enums import QuestionType
from app.persistence.models import ProfessorReviewRow
from app.persistence.repositories import ProfessorReviewRepository
from app.subjects.resolve import key_of_version, storage_keys_by_version

#: Reviews counted per type. Enough to show a pattern.
REVIEW_LIMIT = 60


def reviews_for_type(
    session: Session, question_type: QuestionType, *, subject: str = LEGACY_SUBJECT
) -> list[ProfessorReviewRow]:
    """Reviews of this subject's questions of this type, newest first, capped at the limit.

    A question's subject is its course's personal key (``SubjectProfile.personal_key``: the
    preset and the course's owner, or ``custom:<course id>``), reached through the curriculum
    version it was generated against. Filtering here is what keeps a Physics course's reviews
    out of the rules a Python course learns, and one professor's out of another's (ADR-059).
    """
    reviews = ProfessorReviewRepository(session).list_with_questions(limit=500)
    of_type = [
        review
        for review in reviews
        if review.question is not None and review.question.question_type is question_type
    ]
    keys = storage_keys_by_version(
        session,
        {
            review.question.curriculum_version_id
            for review in of_type
            if review.question.curriculum_version_id is not None
        },
    )
    matching = [
        review
        for review in of_type
        if key_of_version(keys, review.question.curriculum_version_id) == subject
    ]
    return matching[:REVIEW_LIMIT]
