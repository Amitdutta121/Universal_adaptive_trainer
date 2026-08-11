"""Structured preference extraction and conservative merge."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.domain.enums import PreferenceCategory, PreferenceConfirmationState
from app.domain.preferences import confidence_from_evidence
from app.persistence.models import PreferenceStatementRow
from app.personalization.learner import (
    MIN_SUPPORTING_REVIEWS,
    PreferenceCandidate,
    PreferenceExtractionResult,
    extract_preference_candidates,
    merge_candidates,
)


class FakePreferenceClient:
    """Deterministic structured client for preference extraction tests."""

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


def test_merge_drops_single_supporting_review() -> None:
    candidates = [
        PreferenceCandidate(
            rule_text="Prefer easy questions",
            category=PreferenceCategory.DISLIKE,
            supporting_review_ids=[1],
        )
    ]
    merged = merge_candidates([], candidates)
    assert merged == []


def test_merge_accepts_two_supporting_reviews() -> None:
    candidates = [
        PreferenceCandidate(
            rule_text="Prefer concise prompts.",
            category=PreferenceCategory.WORDING,
            supporting_review_ids=[1, 2],
        )
    ]
    rows = merge_candidates([], candidates)
    assert len(rows) == 1
    assert rows[0].evidence_count == 2
    assert rows[0].confidence >= 0.35
    assert rows[0].confirmation_state is PreferenceConfirmationState.INFERRED
    assert rows[0].supporting_review_ids == [1, 2]


def test_merge_unions_existing_row_on_normalized_rule_text() -> None:
    existing = [
        PreferenceStatementRow(
            id=10,
            rule_text="Prefer concise prompts.",
            category=PreferenceCategory.WORDING,
            evidence_count=2,
            confidence=0.4,
            supporting_review_ids=([1, 2]),
            confirmation_state=PreferenceConfirmationState.INFERRED,
        )
    ]
    candidates = [
        PreferenceCandidate(
            rule_text="  PREFER CONCISE PROMPTS.  ",
            category=PreferenceCategory.WORDING,
            supporting_review_ids=[2, 3],
        )
    ]
    rows = merge_candidates(existing, candidates)
    assert len(rows) == 1
    assert rows[0].id == 10
    assert rows[0].evidence_count == 3
    assert rows[0].supporting_review_ids == [1, 2, 3]
    assert rows[0].confidence >= 0.35


def test_merge_respects_confirmed_boost_on_existing_row() -> None:
    existing = [
        PreferenceStatementRow(
            id=5,
            rule_text="Use real-world scenarios.",
            category=PreferenceCategory.SCENARIO_STYLE,
            evidence_count=2,
            confidence=0.5,
            supporting_review_ids=([1, 2]),
            confirmation_state=PreferenceConfirmationState.CONFIRMED,
        )
    ]
    candidates = [
        PreferenceCandidate(
            rule_text="Use real-world scenarios.",
            category=PreferenceCategory.SCENARIO_STYLE,
            supporting_review_ids=[3, 4],
        )
    ]
    rows = merge_candidates(existing, candidates)
    assert rows[0].evidence_count == 4
    assert rows[0].confidence == confidence_from_evidence(4, confirmed=True)


def test_extract_uses_structured_client() -> None:
    expected = PreferenceExtractionResult(
        preferences=[
            PreferenceCandidate(
                rule_text="Prefer application over recall.",
                category=PreferenceCategory.EMPHASIS,
                supporting_review_ids=[1, 2],
            )
        ]
    )
    client = FakePreferenceClient(expected)
    result = extract_preference_candidates(client, reviews_payload="review batch")
    assert result.preferences
    assert len(client.calls) == 1
    assert client.calls[0]["model"] is PreferenceExtractionResult
    assert "professor reviews" in client.calls[0]["system"].lower()
    assert client.calls[0]["prompt"] == "review batch"


def test_min_supporting_reviews_is_two() -> None:
    assert MIN_SUPPORTING_REVIEWS == 2
