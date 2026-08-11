"""Preference statement and review embedding persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.enums import (
    PreferenceCategory,
    PreferenceConfirmationState,
    QuestionStatus,
    ReviewDecision,
)
from app.domain.preferences import encode_review_ids
from app.feedback import submit_review
from app.persistence.models import (
    PreferenceStatementRow,
    ProfessorReviewRow,
    QuestionRow,
    ReviewEmbeddingRow,
)
from app.persistence.repositories import (
    PreferenceRepository,
    QuestionRepository,
    ReviewEmbeddingRepository,
)


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


def _seed_reviewed_question(session: Session) -> ProfessorReviewRow:
    question = _question(session)
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.APPROVE,
        comment="Good.",
    )
    session.commit()
    assert review.id is not None
    return review


def test_preference_round_trip(session: Session) -> None:
    repo = PreferenceRepository(session)
    row = repo.add(
        PreferenceStatementRow(
            rule_text="Prefer application over recall.",
            category=PreferenceCategory.EMPHASIS,
            evidence_count=2,
            confidence=0.4,
            supporting_review_ids_json=encode_review_ids([1, 2]),
            active=True,
            confirmation_state=PreferenceConfirmationState.INFERRED,
            profile_version="1",
        )
    )
    session.commit()
    assert PreferenceRepository(session).get(row.id).rule_text.startswith("Prefer")


def test_embedding_upsert(session: Session) -> None:
    review = _seed_reviewed_question(session)
    repo = ReviewEmbeddingRepository(session)
    row = repo.upsert(
        ReviewEmbeddingRow(
            review_id=review.id,
            model_id="fake/embeddings",
            vector_json="[0.1, 0.2]",
            content_hash="abc",
        )
    )
    session.commit()
    assert ReviewEmbeddingRepository(session).get_for_review(review.id).id == row.id
