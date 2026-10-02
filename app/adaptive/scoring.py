"""Turn a student's submitted answer into a 0-100 score.

Responsibility
    Grade one answer through the isolated capability graders (``graders/``, ADR-055):
    :mod:`app.assessment.specs` says which capability grades the question and with what spec,
    the grader returns 0-1, and this module reports it on the app's 0-100 scale. A testable
    programming question still scores ``passed_tests / total_tests * 100``; a naturally discrete
    question scores 0 or 100.

A malformed answer is a **wrong answer, not an error**. A student who types
``banana`` where an option index was expected has answered incorrectly; raising
would turn their mistake into a failed request and lose the attempt. Only a
question that *cannot be marked at all* -- no options, no test cases -- raises,
because that is a defect in an approved question rather than in the answer.

The behaviour is the scorer's from before the move, unchanged:
``tests/test_grader_replay.py`` replays answers through a frozen copy of the old scorer
(``tests/grading_oracle.py``) and through this one and requires identical results.

Allowed dependencies
    ``app.domain``, ``app.errors``, ``app.assessment``, ``graders``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.assessment.specs import Unmarkable, plan_for
from app.domain.mastery import MAX_SCORE
from app.domain.questions import Question
from app.errors import CodeExecutionUnavailableError, DomainRuleError
from graders import ExecutorError, SpecError, get_grader

logger = logging.getLogger(__name__)

#: Capabilities whose result is a fraction of tests, reported with test counts.
_TESTED_CAPABILITIES = frozenset({"code.python.tests"})


@dataclass(frozen=True)
class ScoredAnswer:
    """What one submitted answer was worth."""

    score: float
    #: Populated only for executable types, so a 60 is readable as 3/5 rather
    #: than 6/10. ``None`` for discrete types, which have no test fraction.
    passed_tests: int | None = None
    total_tests: int | None = None
    #: What to show the student afterwards: failing-test evidence for an
    #: executable type, the author's explanation for a discrete one.
    detail: str | None = None


def _unmarkable(question: Question, what: str) -> DomainRuleError:
    return DomainRuleError(
        "This question cannot be marked, so it should not have been served.",
        detail=f"Question {question.id}: {what}.",
    )


def score_answer(question: Question, answer: str) -> ScoredAnswer:
    """Score ``answer`` against ``question``.

    Raises:
        DomainRuleError: if the question carries no assessment format, or its
            stored content is missing what marking requires.
        CodeExecutionUnavailableError: the answer's code could not be run at all.
    """
    if question.question_type is None:
        raise DomainRuleError(
            "This question has no assessment format, so an answer cannot be scored.",
            detail=f"Question {question.id}.",
        )
    try:
        plan = plan_for(question.question_type, question.content or {}, question.tests)
    except Unmarkable as reason:
        raise _unmarkable(question, str(reason)) from reason

    try:
        grader = get_grader(plan.capability)
    except KeyError as reason:
        raise _unmarkable(question, f"no grader is built for {plan.capability}") from reason
    try:
        result = grader.grade(plan.spec, plan.rewrite_answer(answer))
    except SpecError as reason:
        raise _unmarkable(question, str(reason)) from reason
    except ExecutorError as reason:
        # The sandbox could not run the answer. Not the student's fault: raise before anything
        # is recorded, so the attempt stays open and can be resubmitted. The reason names the
        # sandbox, so it is logged, not sent to the student.
        logger.error("Could not run an answer to question %s: %s", question.id, reason)
        raise CodeExecutionUnavailableError(
            "Your answer could not be run right now. Please submit it again in a moment.",
            detail=f"Question {question.id}.",
        ) from reason

    score = result.score * MAX_SCORE
    if plan.capability in _TESTED_CAPABILITIES:
        passed = sum(1 for test in result.tests if test.passed)
        logger.info(
            "Scored question %s: %s/%s tests passed.", question.id, passed, len(result.tests)
        )
        return ScoredAnswer(
            score=score,
            passed_tests=passed,
            total_tests=len(result.tests),
            detail=result.feedback,
        )
    return ScoredAnswer(score=score, detail=result.feedback)


__all__ = ["ScoredAnswer", "score_answer"]
