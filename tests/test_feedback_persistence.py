from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.domain.enums import RejectionReason, ReviewDecision
from app.domain.feedback import encode_reasons
from app.persistence.models import ProfessorReviewRow, QuestionRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository


def test_review_row_stores_reasons_and_edit_snapshot(session: Session) -> None:
    question = QuestionRepository(session).add(
        QuestionRow(prompt="Old prompt.", original_prompt="Old prompt.")
    )
    session.flush()
    review = ProfessorReviewRow(
        question_id=question.id,
        decision=ReviewDecision.EDIT,
        reasons_json=encode_reasons([RejectionReason.POOR_WORDING]),
        comment="Clarify.",
        edited_prompt="New prompt.",
        edited_reference_solution="print(1)",
        edited_tests="",
        changed_fields_json=json.dumps(["prompt"]),
        professor_id=None,
        reviewed_generator_name="base",
        reviewed_generator_version="1",
    )
    ProfessorReviewRepository(session).add(review)
    session.commit()

    loaded = ProfessorReviewRepository(session).list_recent()[0]
    assert loaded.reasons_json is not None
    assert loaded.edited_prompt == "New prompt."
    assert loaded.edited_tests == ""
    assert json.loads(loaded.changed_fields_json) == ["prompt"]


def test_count_by_decision_and_reason_counts(session: Session) -> None:
    q = QuestionRepository(session).add(QuestionRow(prompt="Q", original_prompt="Q"))
    session.flush()
    repo = ProfessorReviewRepository(session)
    repo.add(
        ProfessorReviewRow(
            question_id=q.id,
            decision=ReviewDecision.APPROVE,
            reasons_json="[]",
        )
    )
    repo.add(
        ProfessorReviewRow(
            question_id=q.id,
            decision=ReviewDecision.REJECT,
            reasons_json=encode_reasons([RejectionReason.TOO_EASY, RejectionReason.AMBIGUOUS]),
        )
    )
    repo.add(
        ProfessorReviewRow(
            question_id=q.id,
            decision=ReviewDecision.EDIT,
            reasons_json=encode_reasons([RejectionReason.TOO_EASY]),
            edited_prompt="Q2",
            edited_reference_solution="",
            edited_tests="",
            changed_fields_json='["prompt"]',
        )
    )
    session.commit()

    assert repo.count_by_decision() == {"approve": 1, "reject": 1, "edit": 1}
    assert repo.reason_counts() == {"too_easy": 2, "ambiguous": 1}
