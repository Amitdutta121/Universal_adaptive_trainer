"""Orchestrate preference refresh and professor confirm/correct/remove actions."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.enums import PreferenceConfirmationState, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS
from app.domain.preferences import confidence_from_evidence
from app.errors import DomainRuleError
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import PreferenceStatementRow, ProfessorReviewRow
from app.persistence.repositories import PreferenceRepository, ProfessorReviewRepository
from app.personalization.learner import extract_preference_candidates, merge_candidates

REVIEW_LIMIT = 50
PROMPT_SNIPPET_CHARS = 240


def _now() -> datetime:
    return datetime.now(UTC)


def _example_prompt(review: ProfessorReviewRow) -> str:
    if review.decision == ReviewDecision.EDIT and review.edited_prompt:
        return review.edited_prompt
    return review.question.prompt


def _select_reviews_for_extraction(session: Session) -> list[ProfessorReviewRow]:
    repo = ProfessorReviewRepository(session)
    recent = repo.list_with_questions(limit=200)
    edits = [review for review in recent if review.decision == ReviewDecision.EDIT]
    others = [review for review in recent if review.decision != ReviewDecision.EDIT]
    return (edits + others)[:REVIEW_LIMIT]


def serialize_reviews_for_extraction(reviews: list[ProfessorReviewRow]) -> str:
    """Build a compact JSON payload for structured preference extraction."""
    entries: list[dict[str, object]] = []
    for review in reviews:
        prompt = _example_prompt(review)
        snippet = prompt[:PROMPT_SNIPPET_CHARS] if prompt else None
        reasons = review.reasons
        entries.append(
            {
                "review_id": review.id,
                "decision": str(review.decision),
                "reasons": [REJECTION_REASON_LABELS[reason] for reason in reasons],
                "comment": review.comment.strip() if review.comment else None,
                "prompt_snippet": snippet,
                "changed_fields": review.changed_fields,
            }
        )
    return json.dumps(entries, separators=(",", ":"))


def refresh_preferences(
    session: Session,
    *,
    client: StructuredLLMClient | None = None,
) -> int:
    """Re-infer preferences from recent reviews and return the active count."""
    reviews = _select_reviews_for_extraction(session)
    if not reviews:
        return len(PreferenceRepository(session).list_all(active_only=True))

    llm = client or get_structured_client()
    payload = serialize_reviews_for_extraction(reviews)
    extraction = extract_preference_candidates(llm, payload)

    pref_repo = PreferenceRepository(session)
    existing = pref_repo.list_all()
    changed = merge_candidates(existing, extraction.preferences)
    for row in changed:
        if row.id is None:
            pref_repo.add(row)
    session.commit()
    return len(pref_repo.list_all(active_only=True))


def list_active_preferences(session: Session) -> list[PreferenceStatementRow]:
    return PreferenceRepository(session).list_all(active_only=True)


def confirm_preference(session: Session, preference_id: int) -> PreferenceStatementRow:
    repo = PreferenceRepository(session)
    row = repo.get(preference_id)
    row.confirmation_state = PreferenceConfirmationState.CONFIRMED
    row.confidence = confidence_from_evidence(row.evidence_count, confirmed=True)
    row.updated_at = _now()
    session.commit()
    return row


def correct_preference(
    session: Session,
    preference_id: int,
    rule_text: str,
) -> PreferenceStatementRow:
    cleaned = rule_text.strip()
    if not cleaned:
        raise DomainRuleError("Corrected preference text must not be empty.")

    repo = PreferenceRepository(session)
    row = repo.get(preference_id)
    row.rule_text = cleaned
    row.confirmation_state = PreferenceConfirmationState.CORRECTED
    row.confidence = max(
        row.confidence,
        confidence_from_evidence(row.evidence_count, confirmed=True),
    )
    row.updated_at = _now()
    session.commit()
    return row


def remove_preference(session: Session, preference_id: int) -> PreferenceStatementRow:
    repo = PreferenceRepository(session)
    row = repo.get(preference_id)
    row.active = False
    row.updated_at = _now()
    session.commit()
    return row
