"""Write a review into memory as an episode, and say what it teaches (ADR-063 point 3).

An episode freezes what the professor reviewed and what they said about it, together with
every judge's verdict on the same question at that moment, so the generator (examples, and
"rejected because ...") and later the judges (m11) learn from the same rows. Recording one
makes no model call and no embedding call: retrieval reuses the question's cached vector
(``question_embeddings``).

A round question the professor approved also leaves one **retry episode** per failed attempt
(m6): what the attempt got wrong and what it was told, shown to later targets of the same
type and subtopic as "avoid: ...".
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionType, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS
from app.domain.questions import GenerationAttempt
from app.memory.repository import MemoryEpisodeRepository
from app.persistence.models import MemoryEpisodeRow, ProfessorReviewRow, QuestionRow
from app.retrieval.duplicates import embed_text
from app.subjects import profile_for_version

#: ``MemoryEpisodeRow.source`` of an episode written from a professor review.
SOURCE_REVIEW = "review"
#: ``MemoryEpisodeRow.source`` of a failed attempt of a round question the professor approved.
SOURCE_RETRY = "retry"
#: ``MemoryEpisodeRow.source`` of a verdict on a judge-rejected audit draft (m9).
SOURCE_AUDIT = "audit"
#: ``MemoryEpisodeRow.source`` of a verdict on a borderline-kept judge failure (m10).
SOURCE_BORDERLINE = "borderline"

#: Retry lessons shown per target.
MAX_RETRY_LESSONS = 3

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
    session: Session,
    review: ProfessorReviewRow,
    reviewed: ReviewedQuestion,
    *,
    source: str | None = None,
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
            source=source or (SOURCE_AUDIT if question.audit else SOURCE_REVIEW),
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


def _attempt_lesson(attempt: GenerationAttempt) -> tuple[str, str | None] | None:
    """What a failed attempt got wrong, and what it was told to do; ``None`` if nothing.

    An unreadable reply teaches nothing about the question, so it is left out.
    """
    if attempt.usable or attempt.malformed:
        return None
    wrong = [check.detail or check.name for check in attempt.failed_checks]
    if not attempt.accepted and attempt.detail:
        wrong.insert(0, attempt.detail)
    if not wrong:
        return None
    fix = " ".join(check.evidence for check in attempt.failed_checks if check.evidence)
    return "; ".join(wrong), fix or None


def record_retry_episodes(session: Session, review: ProfessorReviewRow) -> list[MemoryEpisodeRow]:
    """Turn the failed attempts of an approved round question into retry episodes (m6).

    A round question is one generated for a target subtopic. One episode per failed attempt,
    filed under that subtopic and the requested difficulty, without a review id (the
    review's own episode holds it). A rejected question teaches nothing: its fix was not
    good enough. Once per question; a repeat returns nothing. No model call.
    """
    question = review.question
    if (
        question.audit
        or review.decision is ReviewDecision.REJECT
        or question.target_subtopic_id is None
    ):
        return []
    repository = MemoryEpisodeRepository(session)
    if repository.of_source(SOURCE_RETRY, question_id=question.id):
        return []
    spec = question.spec if isinstance(question.spec, dict) else {}
    difficulty = Difficulty(spec.get("difficulty") or question.difficulty)
    subtopic_ids = [question.target_subtopic_id]
    subject = profile_for_version(session, question.curriculum_version_id).personal_key
    episodes: list[MemoryEpisodeRow] = []
    for attempt in question.generation_attempts or []:
        lesson = _attempt_lesson(attempt)
        if lesson is None:
            continue
        wrong, fix = lesson
        episodes.append(
            repository.add(
                MemoryEpisodeRow(
                    question_id=question.id,
                    source=SOURCE_RETRY,
                    subject=subject,
                    question_type=question.question_type,
                    topic_id=question.topic_id,
                    subtopic_ids=subtopic_ids,
                    difficulty=difficulty,
                    text=wrong,
                    decision=review.decision,
                    comment=fix,
                    judge_verdicts={},
                )
            )
        )
    return episodes


def retry_lessons(
    session: Session,
    *,
    subject: str,
    question_type: QuestionType,
    subtopic_id: int,
    difficulty: Difficulty,
    limit: int = MAX_RETRY_LESSONS,
    exclude_question_ids: Collection[int] = (),
) -> list[str]:
    """The "avoid" lines for a target, from retry episodes of its type and subtopic.

    Only questions still approved count. The target's difficulty first, then newest first;
    the same lesson is shown once.
    """
    rows = MemoryEpisodeRepository(session).of_source(
        SOURCE_RETRY,
        subject=subject,
        question_type=question_type,
        approved_only=True,
        exclude_question_ids=exclude_question_ids,
    )
    rows = sorted(
        (row for row in rows if subtopic_id in (row.subtopic_ids or [])),
        key=lambda row: row.difficulty != difficulty,
    )
    lines = dict.fromkeys(
        f"({row.difficulty.value}) {row.text}" + (f" -- {row.comment}" if row.comment else "")
        for row in rows
    )
    return list(lines)[:limit]


def rejection_because(episode: MemoryEpisodeRow) -> str:
    """Why the professor rejected it: the reason labels, then the comment. ``""`` if neither."""
    parts = [REJECTION_REASON_LABELS[reason] for reason in episode.reasons or []]
    if episode.comment:
        parts.append(episode.comment)
    return "; ".join(parts)
