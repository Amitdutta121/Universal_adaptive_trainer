"""Preference refresh and professor confirm/correct/remove actions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.enums import (
    PreferenceCategory,
    PreferenceConfirmationState,
    QuestionStatus,
    RejectionReason,
    ReviewDecision,
)
from app.domain.preferences import encode_review_ids
from app.feedback import submit_review
from app.persistence.models import PreferenceStatementRow, QuestionRow
from app.persistence.repositories import PreferenceRepository, QuestionRepository
from app.personalization.learner import (
    PreferenceCandidate,
    PreferenceExtractionResult,
)
from app.personalization.service import (
    confirm_preference,
    correct_preference,
    refresh_preferences,
    remove_preference,
)


class FakePreferenceClient:
    """Deterministic structured client for preference service tests."""

    def __init__(self, result: PreferenceExtractionResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    @property
    def description(self) -> str:
        return "fake/preference-model"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        self.calls.append({"system": system, "prompt": prompt, "model": response_model})
        return self.result


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


def _seed_reviews(session: Session) -> list[int]:
    ids: list[int] = []
    for idx in range(2):
        question = _question(session, prompt=f"Prompt {idx}.")
        review = submit_review(
            session,
            question_id=question.id,
            decision=ReviewDecision.REJECT,
            reasons=[RejectionReason.POOR_WORDING],
            comment=f"Too verbose {idx}.",
        )
        session.commit()
        assert review.id is not None
        ids.append(review.id)
    return ids


def test_refresh_persists_merged_preferences(session: Session) -> None:
    review_ids = _seed_reviews(session)
    fake_client = FakePreferenceClient(
        PreferenceExtractionResult(
            preferences=[
                PreferenceCandidate(
                    rule_text="Prefer concise prompts.",
                    category=PreferenceCategory.WORDING,
                    supporting_review_ids=review_ids,
                )
            ]
        )
    )

    n = refresh_preferences(session, client=fake_client)
    session.commit()

    assert n >= 1
    rows = PreferenceRepository(session).list_all()
    assert rows
    assert fake_client.calls
    assert str(review_ids[0]) in fake_client.calls[0]["prompt"]


def test_confirm_correct_remove(session: Session) -> None:
    row = PreferenceRepository(session).add(
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

    confirm_preference(session, row.id)
    session.commit()
    confirmed = PreferenceRepository(session).get(row.id)
    assert confirmed.confirmation_state is PreferenceConfirmationState.CONFIRMED
    assert confirmed.active is True

    correct_preference(session, row.id, "Prefer short realistic programs.")
    session.commit()
    corrected = PreferenceRepository(session).get(row.id)
    assert corrected.rule_text == "Prefer short realistic programs."
    assert corrected.confirmation_state is PreferenceConfirmationState.CORRECTED

    remove_preference(session, row.id)
    session.commit()
    removed = PreferenceRepository(session).get(row.id)
    assert removed.active is False
    assert removed.confirmation_state is PreferenceConfirmationState.CORRECTED
