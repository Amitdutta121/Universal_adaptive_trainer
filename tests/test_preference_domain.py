from app.domain.enums import PreferenceCategory, PreferenceConfirmationState
from app.domain.preferences import PreferenceStatement, confidence_from_evidence


def test_confidence_requires_repeated_evidence() -> None:
    assert confidence_from_evidence(1) < 0.35
    assert confidence_from_evidence(2) >= 0.35
    assert confidence_from_evidence(10) > confidence_from_evidence(2)


def test_preference_statement_defaults() -> None:
    stmt = PreferenceStatement(
        rule_text="Prefer concise prompts.",
        category=PreferenceCategory.WORDING,
        evidence_count=2,
        confidence=0.4,
        supporting_review_ids=[1, 2],
    )
    assert stmt.active is True
    assert stmt.confirmation_state is PreferenceConfirmationState.INFERRED
    assert stmt.profile_version == "1"
