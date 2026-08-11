"""Extract and merge professor preference rules from review history."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.domain.enums import PreferenceCategory, PreferenceConfirmationState
from app.domain.preferences import (
    PROFILE_VERSION,
    confidence_from_evidence,
    decode_review_ids,
    encode_review_ids,
)
from app.llm import StructuredLLMClient
from app.persistence.models import PreferenceStatementRow

MIN_SUPPORTING_REVIEWS = 2

SYSTEM = (
    "Infer stable pedagogical preference rules from professor reviews. "
    "Only propose rules supported by repeated evidence across multiple reviews. "
    "Never propose difficulty preference from a single too_easy/too_difficult reject. "
    "Do not invent correctness rules; those are global. "
    "Return structured preferences only."
)


class PreferenceCandidate(BaseModel):
    rule_text: str = Field(min_length=1)
    category: PreferenceCategory
    supporting_review_ids: list[int] = Field(default_factory=list)


class PreferenceExtractionResult(BaseModel):
    preferences: list[PreferenceCandidate] = Field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_rule_text(rule_text: str) -> str:
    return rule_text.strip().casefold()


def extract_preference_candidates(
    client: StructuredLLMClient,
    reviews_payload: str,
) -> PreferenceExtractionResult:
    """Ask the structured LLM to propose preference rules from review text."""
    return client.complete_structured(
        system=SYSTEM,
        prompt=reviews_payload,
        response_model=PreferenceExtractionResult,
    )


def merge_candidates(
    existing: list[PreferenceStatementRow],
    candidates: list[PreferenceCandidate],
) -> list[PreferenceStatementRow]:
    """Merge extracted candidates into stored rows; drop single-evidence rules."""
    changed: list[PreferenceStatementRow] = []

    for candidate in candidates:
        review_ids = sorted(set(candidate.supporting_review_ids))
        if len(review_ids) < MIN_SUPPORTING_REVIEWS:
            continue

        normalized = _normalize_rule_text(candidate.rule_text)
        match = next(
            (row for row in existing if _normalize_rule_text(row.rule_text) == normalized),
            None,
        )

        if match is not None:
            merged_ids = sorted(
                set(decode_review_ids(match.supporting_review_ids_json)) | set(review_ids)
            )
            match.supporting_review_ids_json = encode_review_ids(merged_ids)
            match.evidence_count = len(merged_ids)
            match.confidence = confidence_from_evidence(
                match.evidence_count,
                confirmed=match.confirmation_state is PreferenceConfirmationState.CONFIRMED,
            )
            match.updated_at = _now()
            if match not in changed:
                changed.append(match)
            continue

        row = PreferenceStatementRow(
            rule_text=candidate.rule_text.strip(),
            category=candidate.category,
            evidence_count=len(review_ids),
            confidence=confidence_from_evidence(len(review_ids)),
            supporting_review_ids_json=encode_review_ids(review_ids),
            active=True,
            confirmation_state=PreferenceConfirmationState.INFERRED,
            profile_version=PROFILE_VERSION,
        )
        existing.append(row)
        changed.append(row)

    return changed
