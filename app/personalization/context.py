"""Build personalization prompt blocks and transparency payloads."""

from __future__ import annotations

from app.domain.enums import ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS
from app.domain.preferences import PROFILE_VERSION
from app.persistence.models import PreferenceStatementRow
from app.personalization.retrieval import RetrievalResult, RetrievedExample

SOFT_PREF_FLOOR = 0.35
MAX_PREFS_IN_PROMPT = 5

STYLE_PEDAGOGY_DISCLAIMER = (
    "Professor preferences and retrieved review examples affect style and pedagogy only. "
    "They must not override correctness, executable tests, or grounding in the supplied "
    "textbook section."
)


def _format_preference(pref: PreferenceStatementRow) -> str:
    return f"- [{pref.category.value}] {pref.rule_text}"


def _format_positive_example(example: RetrievedExample) -> str:
    label = "Edited" if example.decision is ReviewDecision.EDIT else "Approved"
    lines = [f"- ({label}, review #{example.review_id}) {example.prompt}"]
    if example.comment:
        lines.append(f"  Comment: {example.comment.strip()}")
    return "\n".join(lines)


def _format_rejected_example(example: RetrievedExample) -> str:
    reason_labels = [REJECTION_REASON_LABELS[reason] for reason in example.reasons]
    reasons = ", ".join(reason_labels) if reason_labels else "No reasons recorded"
    lines = [f"- (Rejected, review #{example.review_id}) {example.prompt}"]
    lines.append(f"  Reasons: {reasons}")
    if example.comment:
        lines.append(f"  Comment: {example.comment.strip()}")
    return "\n".join(lines)


def build_personalization_prompt_blocks(
    *,
    preferences: list[PreferenceStatementRow],
    retrieval: RetrievalResult,
) -> str:
    """Format preference bullets and retrieved example blocks for the user prompt."""
    blocks: list[str] = []

    selected_prefs = preferences[:MAX_PREFS_IN_PROMPT]
    if selected_prefs:
        pref_lines = "\n".join(_format_preference(pref) for pref in selected_prefs)
        blocks.append(f"Professor preferences:\n{pref_lines}")

    if retrieval.approved_or_edited:
        example_lines = "\n".join(
            _format_positive_example(example) for example in retrieval.approved_or_edited
        )
        blocks.append(f"Approved or edited examples to emulate:\n{example_lines}")

    if retrieval.rejected:
        example_lines = "\n".join(
            _format_rejected_example(example) for example in retrieval.rejected
        )
        blocks.append(f"Rejected examples to avoid:\n{example_lines}")

    if not blocks:
        return ""

    return "\n\n".join(blocks)


def transparency_payload(
    *,
    preference_ids: list[int],
    review_ids: list[int],
) -> dict[str, object]:
    """The non-chain-of-thought personalization evidence stamped on questions."""
    return {
        "preference_ids": preference_ids,
        "retrieved_review_ids": review_ids,
        "profile_version": PROFILE_VERSION,
        "generator": "personalized-context@1",
    }
