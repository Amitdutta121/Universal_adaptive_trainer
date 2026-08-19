"""The adaptive engine: serve the next question, fold in the score.

Responsibility
    Assemble the pure pieces (:mod:`app.adaptive.selection`,
    :mod:`app.adaptive.state`, :mod:`app.adaptive.scoring`) and the repositories
    into the adaptive loop:

    1. weakness-weighted roulette picks a subtopic;
    2. that subtopic's topic mastery picks a difficulty;
    3. the cell's highest-priority question is served, and its priority drops;
    4. the score updates the topic's BKT state and every subtopic's weakness.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.persistence``,
    ``app.validation``. Must not import ``app.generation``,
    ``app.personalization`` or ``app.web``.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.adaptive.scoring import ScoredAnswer, score_answer
from app.adaptive.selection import (
    Candidate,
    choose_subtopic,
    difficulty_fallback_order,
    rank_candidates,
)
from app.adaptive.state import update_mastery, update_weakness
from app.domain.enums import Difficulty
from app.domain.mastery import difficulty_for_mastery
from app.domain.questions import LOWEST_PRIORITY, Question
from app.errors import DomainRuleError, NoQuestionAvailableError
from app.persistence.models import QuestionRow, StudentAttemptRow, TrainingSessionRow
from app.persistence.repositories import (
    CurriculumRepository,
    QuestionRepository,
    QuestionSetRepository,
    StudentAttemptRepository,
    StudentStateRepository,
    TrainingSessionRepository,
)
from app.validation.runner import LocalCodeRunner

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServedQuestion:
    """A question handed to a student, and the attempt row recording that."""

    attempt: StudentAttemptRow
    question: QuestionRow
    #: True when the cell the roulette asked for was empty and the engine had to
    #: relax difficulty or redraw. Surfaced rather than hidden: a bank with gaps
    #: otherwise reads as a bank that chose these questions deliberately.
    fallback_used: bool = False
    #: Set when this is a question the session was already waiting on rather than
    #: a fresh draw.
    resumed: bool = False


@dataclass(frozen=True)
class AnsweredAttempt:
    """The result of scoring one submitted answer."""

    attempt: StudentAttemptRow
    scored: ScoredAnswer
    mastery_before: float | None
    mastery_after: float | None


class AdaptiveTrainingEngine:
    """Selects the next question for a student and folds in the resulting score."""

    def __init__(self, session: Session, runner: LocalCodeRunner | None = None) -> None:
        self._session = session
        self._runner = runner
        self._runs = TrainingSessionRepository(session)
        self._attempts = StudentAttemptRepository(session)
        self._state = StudentStateRepository(session)
        self._sets = QuestionSetRepository(session)
        self._questions = QuestionRepository(session)
        self._curriculum = CurriculumRepository(session)

    # ---------------------------------------------------------------- serving

    def serve_next(self, training_session_id: int) -> ServedQuestion:
        """Draw and serve the next question for a training session.

        Idempotent while a question is outstanding: asking again returns the
        question already served rather than drawing a new one. Otherwise
        reloading the page would abandon the open attempt and let a student skip
        anything they disliked -- a selection bias the mastery estimate cannot
        see.

        Raises:
            NotFoundError: if the session does not exist.
            DomainRuleError: if the session has ended, or lost its question set.
            NoQuestionAvailableError: if no subtopic in the set can be served.
        """
        run = self._runs.get(training_session_id)
        if run.ended_at is not None:
            raise DomainRuleError(
                "This training session has ended.",
                detail=f"Session {run.id} ended at {run.ended_at.isoformat()}.",
            )
        if run.set_version_id is None:
            raise DomainRuleError(
                "This training session's question set no longer exists.",
                detail=(
                    f"Session {run.id} was pinned to a set that has been deleted. "
                    "Start a new session against a current set."
                ),
            )

        open_attempt = self._attempts.open_attempt(run.id)
        if open_attempt is not None:
            return ServedQuestion(
                attempt=open_attempt,
                question=self._questions.get(open_attempt.question_id),
                resumed=True,
            )

        return self._draw(run)

    def _draw(self, run: TrainingSessionRow) -> ServedQuestion:
        """Roulette, difficulty, candidate -- with the ADR-041 fallbacks."""
        set_version_id = run.set_version_id
        assert set_version_id is not None  # checked by the caller

        servable = self._sets.servable_subtopic_ids(set_version_id)
        if not servable:
            raise NoQuestionAvailableError(
                "This question set has no approved questions to serve.",
                detail=(
                    f"Set {set_version_id} holds no approved question tagged with any subtopic. "
                    "Approve questions, then freeze a new set."
                ),
            )

        ordinal = self._attempts.next_ordinal(run.id)
        # Seeded from the session and the position, so a run replays exactly
        # without any generator state being carried between requests.
        rng = random.Random(f"{run.rng_seed}:{ordinal}")

        weights = self._state.weaknesses_for(run.student_id, servable)
        topic_of = self._curriculum.topic_ids_for(servable)
        answered = self._attempts.answered_question_ids(run.student_id)

        fallback_used = False
        while weights:
            subtopic_id = choose_subtopic(weights, rng)
            topic_id = topic_of.get(subtopic_id)
            if topic_id is None:
                # The subtopic was deleted between the two queries above.
                weights.pop(subtopic_id)
                continue

            mastery = self._state.mastery_for(run.student_id, topic_id)
            requested = difficulty_for_mastery(mastery)

            picked = self._pick_in_subtopic(
                set_version_id, subtopic_id=subtopic_id, requested=requested, answered=answered
            )
            if picked is None:
                logger.info(
                    "Session %s: subtopic %s has no question at any difficulty; redrawing.",
                    run.id,
                    subtopic_id,
                )
                weights.pop(subtopic_id)
                fallback_used = True
                continue

            question, served_difficulty = picked
            if served_difficulty is not requested:
                logger.info(
                    "Session %s: subtopic %s had no %s question; serving %s instead.",
                    run.id,
                    subtopic_id,
                    requested.value,
                    served_difficulty.value,
                )
                fallback_used = True

            return self._serve(
                run,
                question=question,
                ordinal=ordinal,
                subtopic_id=subtopic_id,
                requested=requested,
                served=served_difficulty,
                mastery=mastery,
                fallback_used=fallback_used,
            )

        raise NoQuestionAvailableError(
            "No question in this set could be served.",
            detail=(
                f"Every subtopic in set {set_version_id} was exhausted at every difficulty. "
                "The coverage page names the gaps."
            ),
        )

    def _pick_in_subtopic(
        self,
        set_version_id: int,
        *,
        subtopic_id: int,
        requested: Difficulty,
        answered: set[int],
    ) -> tuple[QuestionRow, Difficulty] | None:
        """Best question for this subtopic, relaxing difficulty if the cell is empty."""
        for difficulty in difficulty_fallback_order(requested):
            rows = self._sets.candidates_for_cell(
                set_version_id, subtopic_id=subtopic_id, difficulty=difficulty
            )
            if not rows:
                continue
            ranked = rank_candidates(
                [
                    Candidate(
                        question_id=question_id,
                        priority=priority,
                        times_used=times_used,
                        answered_by_student=question_id in answered,
                    )
                    for question_id, priority, times_used in rows
                ]
            )
            return self._questions.get(ranked[0].question_id), difficulty
        return None

    def _serve(
        self,
        run: TrainingSessionRow,
        *,
        question: QuestionRow,
        ordinal: int,
        subtopic_id: int,
        requested: Difficulty,
        served: Difficulty,
        mastery: float,
        fallback_used: bool,
    ) -> ServedQuestion:
        """Record the serve: drop the question's priority, open an attempt."""
        # The fixed rule: a served question sinks to the back of the bank so
        # another is preferred next time. Global to the bank, by design.
        question.priority = LOWEST_PRIORITY
        question.times_used = (question.times_used or 0) + 1

        attempt = self._attempts.add(
            StudentAttemptRow(
                session_id=run.id,
                student_id=run.student_id,
                question_id=question.id,
                ordinal=ordinal,
                subtopic_id=subtopic_id,
                requested_difficulty=requested,
                served_difficulty=served,
                mastery_before=mastery,
            )
        )
        logger.info(
            "Session %s served question %s (subtopic %s, %s) as attempt %s.",
            run.id,
            question.id,
            subtopic_id,
            served.value,
            attempt.ordinal,
        )
        return ServedQuestion(
            attempt=attempt, question=question, fallback_used=fallback_used, resumed=False
        )

    # ---------------------------------------------------------------- scoring

    def submit_answer(self, attempt_id: int, answer: str) -> AnsweredAttempt:
        """Score an answer, then update the student's mastery and weaknesses.

        Raises:
            NotFoundError: if the attempt does not exist.
            DomainRuleError: if it was already answered, or cannot be marked.
        """
        attempt = self._attempts.get(attempt_id)
        if attempt.score is not None:
            raise DomainRuleError(
                "This question has already been answered.",
                detail=f"Attempt {attempt.id} was scored at {attempt.answered_at}.",
            )

        row = self._questions.get(attempt.question_id)
        scored = score_answer(Question.model_validate(row), answer, runner=self._runner)

        mastery_before, mastery_after = self._update_mastery(
            student_id=attempt.student_id, topic_id=row.topic_id, score=scored.score
        )
        self._update_weaknesses(
            student_id=attempt.student_id,
            subtopic_ids=list(row.subtopic_ids),
            score=scored.score,
        )

        attempt.answer = answer
        attempt.score = scored.score
        attempt.passed_tests = scored.passed_tests
        attempt.total_tests = scored.total_tests
        attempt.mastery_after = mastery_after
        attempt.answered_at = datetime.now(UTC)
        self._session.flush()

        logger.info(
            "Attempt %s scored %.1f; topic %s mastery %s -> %s.",
            attempt.id,
            scored.score,
            row.topic_id,
            mastery_before,
            mastery_after,
        )
        return AnsweredAttempt(
            attempt=attempt,
            scored=scored,
            mastery_before=mastery_before,
            mastery_after=mastery_after,
        )

    def _update_mastery(
        self, *, student_id: int, topic_id: int | None, score: float
    ) -> tuple[float | None, float | None]:
        """Fold one score into the question's topic. No topic, no update."""
        if topic_id is None:
            # A question that outlived its topic. The weakness update below still
            # applies, so the answer is not wasted.
            logger.warning("Scored an answer for a question with no topic; mastery unchanged.")
            return None, None
        before = self._state.mastery_for(student_id, topic_id)
        after = update_mastery(before, score)
        self._state.record_mastery(student_id, topic_id, after)
        return before, after

    def _update_weaknesses(self, *, student_id: int, subtopic_ids: list[int], score: float) -> None:
        """Fold one score into *every* subtopic the question exercised.

        All of them, not just the one the roulette drew: the question assessed
        each subtopic it was tagged with, so each has been measured.
        """
        if not subtopic_ids:
            return
        current = self._state.weaknesses_for(student_id, subtopic_ids)
        for subtopic_id in subtopic_ids:
            self._state.record_weakness(
                student_id, subtopic_id, update_weakness(current[subtopic_id], score)
            )


__all__ = ["AdaptiveTrainingEngine", "AnsweredAttempt", "ServedQuestion"]
