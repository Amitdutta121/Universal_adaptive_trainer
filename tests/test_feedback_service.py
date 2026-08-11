"""Professor feedback service behavior."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import QuestionStatus, RejectionReason, ReviewDecision
from app.domain.feedback import decode_changed_fields, decode_reasons
from app.errors import DomainRuleError, NotFoundError
from app.feedback import submit_review
from app.persistence.models import QuestionRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository


def _question(session: Session, **overrides: object) -> QuestionRow:
    values = {
        "prompt": "Write a loop.",
        "original_prompt": "Write a loop.",
        "reference_solution": "pass",
        "original_reference_solution": "pass",
        "tests": "assert True",
        "original_tests": "assert True",
        "generator_name": "base-gen",
        "generator_version": "1",
        "status": QuestionStatus.VALIDATION_PASSED,
    }
    values.update(overrides)
    row = QuestionRepository(session).add(QuestionRow(**values))
    session.commit()
    assert row.id is not None
    return row


def test_approve_sets_status_and_ignores_reasons_and_edit_snapshots(session: Session) -> None:
    question = _question(session)
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.APPROVE,
        reasons=[RejectionReason.TOO_EASY],
        comment="  Good  ",
        prompt="ignored",
        reference_solution="ignored",
        tests="ignored",
    )
    session.commit()
    session.refresh(question)

    assert question.status == QuestionStatus.APPROVED
    assert question.prompt == "Write a loop."
    assert decode_reasons(review.reasons_json) == []
    assert review.edited_prompt is None
    assert review.edited_reference_solution is None
    assert review.edited_tests is None
    assert review.changed_fields_json is None
    assert review.comment == "  Good  "
    assert review.reviewed_generator_name == "base-gen"


def test_reject_requires_reasons(session: Session) -> None:
    question = _question(session)

    with pytest.raises(DomainRuleError):
        submit_review(session, question_id=question.id, decision=ReviewDecision.REJECT)


def test_reject_stores_many_reasons_and_ignores_edit_payloads(session: Session) -> None:
    question = _question(session)
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY, RejectionReason.OTHER],
        comment="custom note",
        prompt="ignored",
        reference_solution="ignored",
        tests="ignored",
    )
    session.commit()
    session.refresh(question)

    assert question.status == QuestionStatus.REJECTED
    assert question.prompt == "Write a loop."
    assert decode_reasons(review.reasons_json) == [
        RejectionReason.TOO_EASY,
        RejectionReason.OTHER,
    ]
    assert review.edited_prompt is None
    assert review.edited_reference_solution is None
    assert review.edited_tests is None
    assert review.comment == "custom note"


def test_edit_preserves_originals_and_snapshots_all_fields(session: Session) -> None:
    question = _question(session)
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.EDIT,
        reasons=[RejectionReason.POOR_WORDING],
        prompt="Write a for-loop over a list.",
        reference_solution="pass",
        tests="assert True",
    )
    session.commit()
    session.refresh(question)

    assert question.status == QuestionStatus.APPROVED
    assert question.prompt == "Write a for-loop over a list."
    assert question.original_prompt == "Write a loop."
    assert question.original_reference_solution == "pass"
    assert question.original_tests == "assert True"
    assert review.edited_prompt == "Write a for-loop over a list."
    assert review.edited_reference_solution == "pass"
    assert review.edited_tests == "assert True"
    assert decode_changed_fields(review.changed_fields_json) == ["prompt"]


@pytest.mark.parametrize("missing", ["prompt", "reference_solution", "tests"])
def test_edit_requires_all_fields(session: Session, missing: str) -> None:
    question = _question(session)
    values: dict[str, str | None] = {
        "prompt": "Changed",
        "reference_solution": "",
        "tests": "",
    }
    values[missing] = None

    with pytest.raises(DomainRuleError):
        submit_review(
            session,
            question_id=question.id,
            decision=ReviewDecision.EDIT,
            **values,
        )


def test_edit_accepts_empty_strings_for_unused_fields(session: Session) -> None:
    question = _question(session, reference_solution=None, tests=None)

    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.EDIT,
        prompt="Changed",
        reference_solution="",
        tests="",
    )

    assert review.edited_reference_solution == ""
    assert review.edited_tests == ""
    assert decode_changed_fields(review.changed_fields_json) == ["prompt"]


def test_edit_with_no_changes_errors(session: Session) -> None:
    question = _question(session)

    with pytest.raises(DomainRuleError):
        submit_review(
            session,
            question_id=question.id,
            decision=ReviewDecision.EDIT,
            prompt="Write a loop.",
            reference_solution="pass",
            tests="assert True",
        )


def test_reviews_remain_append_only(session: Session) -> None:
    question = _question(session)
    first = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.APPROVE,
        professor_id=None,
    )
    second = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.AMBIGUOUS],
        professor_id=42,
    )
    session.commit()

    assert first.id != second.id
    assert first.professor_id is None
    assert second.professor_id == 42
    assert ProfessorReviewRepository(session).count() == 2


def test_unknown_question(session: Session) -> None:
    with pytest.raises(NotFoundError):
        submit_review(session, question_id=999, decision=ReviewDecision.APPROVE)
