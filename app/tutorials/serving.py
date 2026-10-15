"""The tutorial blocks a student's run shows (Phase 6, Task 27).

Two moments: after an answer (a wrong one gets ``worked`` blocks; a right one lighter ones as
mastery rises, then none), and before the first question of a topic in the run when the
student's prior mastery of it is low (pre-teaching). Both read only the blocks frozen with the
run's question set and compose them with a seed from the run and the attempt, so a reload
shows the same blocks. A run without a set, or a set without blocks, shows none, and the
student page keeps today's explanation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import MasteryBand
from app.domain.mastery import mastery_band
from app.persistence.models import (
    QuestionRow,
    StudentAttemptRow,
    TrainingSessionRow,
    TutorialBlockRow,
)
from app.subjects import profile_for_version
from app.tutorials.composer import ComposeState, compose, frozen_blocks
from app.tutorials.generator import get_recipes
from app.tutorials.schema import ContentKind

#: A score that counts as a correct answer, as the student page shows it.
CORRECT_SCORE = 100.0

_CODE_KEYS = ("code", "starter_code", "reference_solution")


_K = ContentKind
_BEFORE = [_K.CONCEPT, _K.PROCESS, _K.CODE, _K.MISCONCEPTION]
_AFTER_CODE = [_K.CODE, _K.MISCONCEPTION, _K.PROCESS, _K.CONCEPT]
_AFTER_OTHER = [_K.MISCONCEPTION, _K.CONCEPT, _K.PROCESS, _K.CODE]


def _kinds(question: QuestionRow, *, before: bool) -> list[ContentKind]:
    """Pre-teaching leads with the idea; after a code question, with the code."""
    if before:
        return _BEFORE
    if any((question.content or {}).get(key) for key in _CODE_KEYS):
        return _AFTER_CODE
    return _AFTER_OTHER


def _subtopic_id(attempt: StudentAttemptRow, question: QuestionRow) -> int | None:
    if attempt.subtopic_id is not None:
        return attempt.subtopic_id
    return question.subtopic_ids[0] if question.subtopic_ids else None


def _compose(
    session: Session,
    run: TrainingSessionRow,
    attempt: StudentAttemptRow,
    question: QuestionRow,
    *,
    mastery: float,
    last_correct: bool | None,
    moment: str,
) -> list[TutorialBlockRow]:
    subtopic_id = _subtopic_id(attempt, question)
    if run.set_version_id is None or subtopic_id is None:
        return []
    blocks = frozen_blocks(session, run.set_version_id, subtopic_id)
    if not blocks:
        return []
    subject = profile_for_version(session, question.curriculum_version_id).storage_key
    recipes = {recipe.id: recipe for recipe in get_recipes(subject)}
    return compose(
        blocks,
        recipes,
        ComposeState(
            mastery=mastery,
            last_correct=last_correct,
            content_kinds=_kinds(question, before=last_correct is None),
            seed=f"{run.rng_seed}:{attempt.id}:{moment}",
        ),
    )


def blocks_after_answer(
    session: Session, attempt: StudentAttemptRow, *, mastery: float | None
) -> list[TutorialBlockRow]:
    """The blocks for the result card of an answered attempt."""
    if attempt.score is None:
        return []
    run = session.get(TrainingSessionRow, attempt.session_id)
    question = session.get(QuestionRow, attempt.question_id)
    if run is None or question is None:
        return []
    return _compose(
        session,
        run,
        attempt,
        question,
        mastery=mastery if mastery is not None else 0.0,
        last_correct=attempt.score >= CORRECT_SCORE,
        moment="after",
    )


def preteach_blocks(session: Session, attempt: StudentAttemptRow) -> list[TutorialBlockRow]:
    """Blocks to read before the attempt's question: only for the first question of its topic
    in the run, and only when the student's prior mastery of the topic is low."""
    question = session.get(QuestionRow, attempt.question_id)
    run = session.get(TrainingSessionRow, attempt.session_id)
    if question is None or run is None or question.topic_id is None:
        return []
    prior = attempt.mastery_before
    if prior is None or mastery_band(prior) is not MasteryBand.LOW:
        return []
    earlier = session.scalar(
        select(StudentAttemptRow.id)
        .join(QuestionRow, QuestionRow.id == StudentAttemptRow.question_id)
        .where(
            StudentAttemptRow.session_id == run.id,
            StudentAttemptRow.ordinal < attempt.ordinal,
            QuestionRow.topic_id == question.topic_id,
        )
        .limit(1)
    )
    if earlier is not None:
        return []
    return _compose(
        session, run, attempt, question, mastery=prior, last_correct=None, moment="before"
    )
