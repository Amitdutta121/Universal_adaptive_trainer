"""Student adaptive-training boundary.

Responsibility
    Given a student, choose the next question; given a score, update the
    student's state.

Status
    **Implemented, and reachable end to end.** The pure state transitions
    (:mod:`app.adaptive.state`), the pure selection helpers
    (:mod:`app.adaptive.selection`), the scorer (:mod:`app.adaptive.scoring`) and
    the engine (:mod:`app.adaptive.service`) all exist and are tested; the rules
    they encode are decided in ADR-041. The API enrols students at
    ``/api/students``, starts runs at ``/api/training-sessions`` and scores
    answers at ``/api/attempts/{attempt_id}/answer``. A run is always served
    from a frozen question set (ADR-036), never the live bank. The shared value
    objects the two loops agree on live in :mod:`app.domain.mastery`.

    Traffic is one-way: the web layer calls :func:`get_adaptive_engine` and this
    package never calls back out to it.

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
    ``app.config``, ``app.domain``, ``app.errors``, ``app.persistence``,
    ``app.validation``. The last is what executes a submitted program and reads a
    question's stored test cases; duplicating a runner here would be worse than
    the dependency. Must not import ``app.generation``, ``app.personalization``
    or ``app.web``.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.adaptive.service import AdaptiveTrainingEngine, AnsweredAttempt, ServedQuestion


class AdaptiveEngine(Protocol):
    """Selects the next question for a student and folds in the resulting score.

    The unit of work is a **training session** (ADR-036), not a bare student: a
    run is pinned to one frozen question set, and a served question has to be
    recorded as an attempt before it can be answered. So the two operations take
    a session id and an attempt id rather than the student id an earlier sketch
    of this protocol assumed.
    """

    def serve_next(self, training_session_id: int) -> ServedQuestion:
        """Pick a subtopic by weakness-weighted roulette, derive difficulty from
        BKT mastery, then serve the highest-priority matching question."""
        ...

    def submit_answer(self, attempt_id: int, answer: str) -> AnsweredAttempt:
        """Score the answer, then update BKT mastery and subtopic weaknesses."""
        ...


def get_adaptive_engine(session: Session) -> AdaptiveEngine:
    """Return the engine bound to a database session."""
    return AdaptiveTrainingEngine(session)


__all__ = [
    "AdaptiveEngine",
    "AdaptiveTrainingEngine",
    "AnsweredAttempt",
    "ServedQuestion",
    "get_adaptive_engine",
]
