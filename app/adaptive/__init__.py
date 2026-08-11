"""Student adaptive-training boundary.

Responsibility
    Given a student, choose the next question; given a score, update the
    student's state.

Status
    **Not implemented in this task, by instruction.** This package exists to
    hold the boundary so the engine can be dropped in without touching the
    professor pipeline. The shared value objects it will build on already exist
    in :mod:`app.domain.mastery`.

The mechanism below is a *fixed* design decision. Do not redesign it without an
explicit instruction:

1. Topic mastery is tracked with BKT (Bayesian Knowledge Tracing).
2. Every subtopic carries a weakness value; all weaknesses start equal
   (:data:`~app.domain.mastery.INITIAL_SUBTOPIC_WEAKNESS`).
3. The next subtopic is chosen by weakness-weighted roulette selection --
   exploiting weak areas while still exploring the rest.
4. Difficulty follows BKT topic mastery: low -> easy, medium -> medium,
   high -> hard (:func:`~app.domain.mastery.difficulty_for_mastery`).
5. A question is selected by desired subtopic, desired difficulty, then
   priority.
6. A served question's priority drops to
   :data:`~app.domain.questions.LOWEST_PRIORITY` so unused questions are
   preferred; reuse becomes possible once the others have been used too.
7. Student scores are 0-100. Testable programming questions score
   ``passed_tests / total_tests * 100``
   (:func:`~app.domain.mastery.score_from_tests`); naturally discrete questions
   score 0 or 100.
8. A score updates both the topic's BKT state and the weaknesses of the
   subtopics associated with the question.

Separation of loops
    This loop adapts *to a student*. Professor content optimization
    (:mod:`app.personalization`) adapts *to a professor*. They share the
    question bank and nothing else -- student scores must never feed professor
    preference, and professor preference must never feed student selection
    beyond the questions it produces.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.persistence``.
    Must not import ``app.generation``, ``app.personalization`` or ``app.web``.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.questions import Question
from app.errors import FeatureNotAvailableError


class AdaptiveEngine(Protocol):
    """Selects the next question for a student and folds in the resulting score."""

    def select_next_question(self, student_id: int) -> Question:
        """Pick a subtopic by weakness-weighted roulette, derive difficulty from
        BKT mastery, then take the highest-priority matching question."""
        ...

    def record_score(self, student_id: int, question_id: int, score: float) -> None:
        """Update BKT topic mastery and the question's subtopic weaknesses."""
        ...


class NullAdaptiveEngine:
    """Placeholder engine. Raises so no fake training session appears to work."""

    def select_next_question(self, student_id: int) -> Question:
        raise FeatureNotAvailableError(
            "The student adaptive engine is not implemented yet.",
            detail=f"Requested next question for student {student_id}.",
        )

    def record_score(self, student_id: int, question_id: int, score: float) -> None:
        raise FeatureNotAvailableError(
            "The student adaptive engine is not implemented yet.",
            detail=f"Requested score update for student {student_id}, question {question_id}.",
        )


def get_adaptive_engine() -> AdaptiveEngine:
    """Return the configured engine. Currently always the null implementation."""
    return NullAdaptiveEngine()


__all__ = ["AdaptiveEngine", "NullAdaptiveEngine", "get_adaptive_engine"]
