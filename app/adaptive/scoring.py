"""Turn a student's submitted answer into a 0-100 score.

Responsibility
    One function per assessment format, implementing the fixed scoring rule from
    ``CLAUDE.md``: a testable programming question scores
    ``passed_tests / total_tests * 100``, and a naturally discrete question
    scores 0 or 100.

A malformed answer is a **wrong answer, not an error**. A student who types
``banana`` where an option index was expected has answered incorrectly; raising
would turn their mistake into a failed request and lose the attempt. Only a
question that *cannot be marked at all* -- no options, no test cases -- raises,
because that is a defect in an approved question rather than in the answer.

Allowed dependencies
    ``app.domain``, ``app.errors``, ``app.validation``. The last is what runs the
    submitted code; reading a question's stored test cases and executing them are
    one import (:func:`app.validation.runner.parse_test_cases`), which is what
    keeps :mod:`app.generation` out of the student loop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.domain.enums import QuestionType
from app.domain.mastery import MAX_SCORE, MIN_SCORE, score_from_tests
from app.domain.questions import Question
from app.errors import DomainRuleError
from app.validation.runner import LocalCodeRunner, normalize_output, parse_test_cases

logger = logging.getLogger(__name__)


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


def score_answer(
    question: Question, answer: str, runner: LocalCodeRunner | None = None
) -> ScoredAnswer:
    """Score ``answer`` against ``question``.

    Raises:
        DomainRuleError: if the question carries no assessment format, or its
            stored content is missing what marking requires.
    """
    if question.question_type is None:
        raise DomainRuleError(
            "This question has no assessment format, so an answer cannot be scored.",
            detail=f"Question {question.id}.",
        )

    content = question.content or {}
    match question.question_type:
        case QuestionType.MULTIPLE_CHOICE:
            return _multiple_choice(question, content, answer)
        case QuestionType.TRUE_FALSE:
            return _true_false(question, content, answer)
        case QuestionType.OUTPUT_PREDICTION:
            return _output_prediction(question, content, answer)
        case QuestionType.PARSONS:
            return _parsons(question, content, answer)
        case QuestionType.CODE_COMPLETION | QuestionType.DEBUGGING | QuestionType.CODING:
            return _executable(question, content, answer, runner or LocalCodeRunner())


def _explanation(content: dict) -> str | None:
    text = content.get("explanation")
    return text if isinstance(text, str) and text.strip() else None


def _discrete(correct: bool, content: dict) -> ScoredAnswer:
    """A discrete question is worth all of the marks or none of them."""
    return ScoredAnswer(
        score=MAX_SCORE if correct else MIN_SCORE,
        detail=_explanation(content),
    )


def _unmarkable(question: Question, what: str) -> DomainRuleError:
    return DomainRuleError(
        "This question cannot be marked, so it should not have been served.",
        detail=f"Question {question.id}: {what}.",
    )


def _multiple_choice(question: Question, content: dict, answer: str) -> ScoredAnswer:
    correct_index = content.get("correct_option_index")
    options = content.get("options")
    if not isinstance(correct_index, int) or isinstance(correct_index, bool):
        raise _unmarkable(question, "no correct option is recorded")
    if not isinstance(options, list) or correct_index >= len(options):
        raise _unmarkable(question, "the correct option is not among the options")

    try:
        chosen = int(answer.strip())
    except (AttributeError, ValueError):
        # Not an index at all. Wrong, not broken.
        return _discrete(correct=False, content=content)
    return _discrete(correct=chosen == correct_index, content=content)


def _true_false(question: Question, content: dict, answer: str) -> ScoredAnswer:
    expected = content.get("correct_answer")
    if not isinstance(expected, bool):
        raise _unmarkable(question, "no correct answer is recorded")

    submitted = answer.strip().casefold()
    if submitted not in {"true", "false"}:
        return _discrete(correct=False, content=content)
    return _discrete(correct=(submitted == "true") == expected, content=content)


def _output_prediction(question: Question, content: dict, answer: str) -> ScoredAnswer:
    expected = content.get("expected_output")
    if not isinstance(expected, str):
        raise _unmarkable(question, "no expected output is recorded")

    # Compared the way the runner compares a program's stdout, so a trailing
    # newline or a CRLF does not fail an answer that is right.
    correct = normalize_output(answer) == normalize_output(expected)
    return _discrete(correct=correct, content=content)


def _parsons_order(answer: str) -> list[str]:
    """Read submitted block ids from newline- or comma-separated text."""
    separated = answer.replace(",", "\n")
    return [line.strip() for line in separated.splitlines() if line.strip()]


def _parsons(question: Question, content: dict, answer: str) -> ScoredAnswer:
    """Score a Parsons puzzle on block order.

    Indentation is **not** assessed. The stored ``indents`` are available, but
    nothing collects them from a student yet, and marking against a field the
    answer cannot express would fail every submission. When the ordering UI grows
    indentation this becomes a partial score rather than 0/100.
    """
    correct_order = content.get("correct_order")
    if not isinstance(correct_order, list) or not correct_order:
        raise _unmarkable(question, "no correct block order is recorded")

    return _discrete(correct=_parsons_order(answer) == correct_order, content=content)


def _executable(
    question: Question, content: dict, answer: str, runner: LocalCodeRunner
) -> ScoredAnswer:
    """Run the student's code against the question's own test cases.

    The score is the fraction of cases that passed, which is the fixed rule for
    a testable programming question. A submission that does not parse, crashes,
    or loops forever simply fails its cases and scores accordingly -- there is no
    separate error path, because a student's broken program is a wrong answer.
    """
    cases = parse_test_cases(content.get("tests")) or parse_test_cases(question.tests)
    if cases is None:
        raise _unmarkable(question, "no usable test cases are stored")

    if not answer.strip():
        # Nothing to run. Skip the subprocess and record the zero directly.
        return ScoredAnswer(
            score=MIN_SCORE, passed_tests=0, total_tests=len(cases), detail="No answer submitted."
        )

    summary = runner.run_tests(answer, cases)
    score = score_from_tests(summary.passed_count, summary.total)
    detail = summary.evidence
    if summary.timed_out and not detail:
        detail = "The submission did not finish in time."
    logger.info(
        "Scored question %s: %s/%s tests passed.", question.id, summary.passed_count, summary.total
    )
    return ScoredAnswer(
        score=score,
        passed_tests=summary.passed_count,
        total_tests=summary.total,
        detail=detail,
    )


__all__ = ["ScoredAnswer", "score_answer"]
