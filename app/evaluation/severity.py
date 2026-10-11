"""Which judge failures are clear (retry) vs borderline (keep with a note) (ADR-064, m10)."""

from __future__ import annotations

from collections.abc import Collection

from app.domain.enums import Difficulty, JudgeMetricId, RejectionReason
from app.evaluation.schema import MetricStatus, PedagogicalEvaluation

#: Incorrect answer / tests and technically incorrect force a retry; wording does not.
BLOCKING_ISSUE_CODES: frozenset[RejectionReason] = frozenset(
    {
        RejectionReason.TECHNICALLY_INCORRECT,
        RejectionReason.INCORRECT_ANSWER,
        RejectionReason.INCORRECT_TESTS,
        # Two defensible answers cannot be graded fairly (a student may pick either).
        RejectionReason.AMBIGUOUS,
    }
)

_DIFFICULTY_BAND: dict[Difficulty, int] = {
    Difficulty.EASY: 0,
    Difficulty.MEDIUM: 1,
    Difficulty.HARD: 2,
}


def difficulty_is_clear(requested: Difficulty, proposed: Difficulty) -> bool:
    """Two bands apart is clear; neighbours are borderline."""
    return abs(_DIFFICULTY_BAND[requested] - _DIFFICULTY_BAND[proposed]) >= 2


def subtopic_is_clear(target_id: int, proposed_ids: Collection[int]) -> bool:
    """No overlap with the target is clear; sharing the target is borderline."""
    return target_id not in set(proposed_ids)


def issues_are_clear(codes: Collection[RejectionReason]) -> bool:
    return any(code in BLOCKING_ISSUE_CODES for code in codes)


def borderline_notes(
    evaluation: PedagogicalEvaluation | None,
    *,
    requested_difficulty: Difficulty,
    target_subtopic_id: int,
) -> list[str]:
    """Professor-facing notes for judge failures that were not retried."""
    if evaluation is None:
        return []
    notes: list[str] = []
    difficulty = evaluation.metric(JudgeMetricId.DIFFICULTY)
    if (
        difficulty is not None
        and difficulty.status is MetricStatus.COMPLETED
        and difficulty.passed is False
        and difficulty.proposed_difficulty is not None
        and not difficulty_is_clear(requested_difficulty, difficulty.proposed_difficulty)
    ):
        notes.append(f"difficulty judge thinks this may be {difficulty.proposed_difficulty.value}")
    topic = evaluation.metric(JudgeMetricId.SUBTOPIC)
    proposed = list(topic.proposed_subtopic_ids) if topic is not None else []
    if (
        topic is not None
        and topic.status is MetricStatus.COMPLETED
        and topic.passed is False
        and not subtopic_is_clear(target_subtopic_id, proposed)
    ):
        notes.append("topic judge thinks this may still cover the target subtopic")
    issues = evaluation.metric(JudgeMetricId.ISSUES)
    codes = list(issues.issue_codes) if issues is not None else []
    if (
        issues is not None
        and issues.status is MetricStatus.COMPLETED
        and issues.passed is False
        and codes
        and not issues_are_clear(codes)
    ):
        notes.append("issues judge flagged wording, distractors or usefulness")
    return notes
