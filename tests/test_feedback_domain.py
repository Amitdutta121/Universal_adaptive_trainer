from __future__ import annotations

from app.domain.enums import RejectionReason, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS, ProfessorReview


def test_all_rejection_reasons_have_labels() -> None:
    assert set(REJECTION_REASON_LABELS) == set(RejectionReason)
    assert REJECTION_REASON_LABELS[RejectionReason.OTHER] == "Other"


def test_professor_review_defaults() -> None:
    review = ProfessorReview(decision=ReviewDecision.APPROVE)
    assert review.reasons == []
    assert review.edited_prompt is None
    assert review.changed_fields == []
    assert review.professor_id is None
