"""Write a review into memory as an episode, and say what it teaches (ADR-063 point 3).

An episode freezes what the professor reviewed and what they said about it, together with
every judge's verdict on the same question at that moment, so the generator (examples, and
"rejected because ...") and later the judges (m11) learn from the same rows. Recording one
makes no model call and no embedding call: retrieval reuses the question's cached vector
(``question_embeddings``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS
from app.memory.repository import MemoryEpisodeRepository
from app.persistence.models import MemoryEpisodeRow, ProfessorReviewRow, QuestionRow
from app.retrieval.duplicates import embed_text
from app.subjects import profile_for_version

#: ``MemoryEpisodeRow.source`` of an episode written from a professor review.
SOURCE_REVIEW = "review"

#: The fields of one judge's answer an episode keeps (``MetricResult`` minus its id).
_VERDICT_FIELDS = (
    "status",
    "passed",
    "rationale",
    "issue_codes",
    "proposed_difficulty",
    "proposed_subtopic_ids",
)


@dataclass(frozen=True)
class ReviewedQuestion:
    """The question as the professor saw it, taken before the review changes it."""

    text: str
    difficulty: Difficulty
    topic_id: int | None
    subtopic_ids: list[int]


def snapshot_question(question: QuestionRow) -> ReviewedQuestion:
    """Call before a review edits or reclassifies ``question``."""
    return ReviewedQuestion(
        text=embed_text(question.prompt, question.content),
        difficulty=question.difficulty,
        topic_id=question.topic_id,
        subtopic_ids=list(question.subtopic_ids),
    )


def judge_verdicts(evaluation: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Each judge's answer in a stored ``PedagogicalEvaluation`` blob, keyed by metric id.

    Read from the raw blob, not re-validated: an episode records what was stored, and a blob
    in an older format still says what each judge answered. Anything but an object is empty.
    """
    verdicts: dict[str, dict[str, Any]] = {}
    if not isinstance(evaluation, dict):
        return verdicts
    for metric in evaluation.get("metrics") or []:
        if isinstance(metric, dict) and metric.get("metric"):
            verdicts[str(metric["metric"])] = {key: metric.get(key) for key in _VERDICT_FIELDS}
    return verdicts


def record_review_episode(
    session: Session, review: ProfessorReviewRow, reviewed: ReviewedQuestion
) -> MemoryEpisodeRow:
    """Write the episode for a review just saved. ``reviewed`` is :func:`snapshot_question`
    taken before the review was applied. One per review: a repeat returns the stored one."""
    repository = MemoryEpisodeRepository(session)
    existing = repository.get_for_review(review.id)
    if existing is not None:
        return existing
    question = review.question
    edited = review.decision is ReviewDecision.EDIT
    evaluation = question.pedagogical_eval if isinstance(question.pedagogical_eval, dict) else {}
    return repository.add(
        MemoryEpisodeRow(
            review_id=review.id,
            question_id=question.id,
            source=SOURCE_REVIEW,
            subject=profile_for_version(session, question.curriculum_version_id).personal_key,
            question_type=question.question_type,
            topic_id=reviewed.topic_id,
            subtopic_ids=reviewed.subtopic_ids,
            difficulty=reviewed.difficulty,
            # The edit is already on the question: its current text is the professor's.
            text=embed_text(question.prompt, question.content) if edited else reviewed.text,
            original_text=reviewed.text if edited else None,
            decision=review.decision,
            reasons=list(review.reasons or []),
            comment=(review.comment or "").strip() or None,
            corrected_difficulty=review.corrected_difficulty,
            corrected_subtopic_ids=review.corrected_subtopic_ids,
            judge_verdicts=judge_verdicts(evaluation),
            rubric_version=evaluation.get("rubric_version"),
        )
    )


def rejection_because(episode: MemoryEpisodeRow) -> str:
    """Why the professor rejected it: the reason labels, then the comment. ``""`` if neither."""
    parts = [REJECTION_REASON_LABELS[reason] for reason in episode.reasons or []]
    if episode.comment:
        parts.append(episode.comment)
    return "; ".join(parts)
