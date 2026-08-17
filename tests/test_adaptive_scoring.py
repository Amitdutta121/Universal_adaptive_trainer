"""Scoring a student's submitted answer, one case per assessment format.

The fixed rule from ``CLAUDE.md``: a testable programming question scores
``passed_tests / total_tests * 100``, a discrete one scores 0 or 100. The rule
most easily lost is that a *malformed* answer is wrong rather than an error.
"""

from __future__ import annotations

import json

import pytest

from app.adaptive.scoring import score_answer
from app.domain.enums import Difficulty, QuestionKind, QuestionType
from app.domain.questions import Question
from app.errors import DomainRuleError

#: Two cases an echo program passes and a constant program half-passes, so the
#: test fraction has three distinguishable outcomes.
ECHO_CASES = [
    {"stdin": "1", "stdout": "1"},
    {"stdin": "2", "stdout": "2"},
]


def _question(
    question_type: QuestionType,
    content: dict,
    *,
    kind: QuestionKind = QuestionKind.DISCRETE,
    tests: str | None = None,
) -> Question:
    return Question(
        id=1,
        prompt=content.get("prompt", "A question."),
        question_type=question_type,
        kind=kind,
        difficulty=Difficulty.EASY,
        content=content,
        tests=tests,
    )


class TestMultipleChoice:
    def _mcq(self) -> Question:
        return _question(
            QuestionType.MULTIPLE_CHOICE,
            {
                "prompt": "Which is a list?",
                "options": ["(1,2)", "[1,2]", "{1:2}"],
                "correct_option_index": 1,
                "explanation": "Square brackets build a list.",
            },
        )

    def test_the_correct_index_scores_full_marks(self) -> None:
        assert score_answer(self._mcq(), "1").score == 100.0

    def test_a_wrong_index_scores_nothing(self) -> None:
        assert score_answer(self._mcq(), "0").score == 0.0

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        assert score_answer(self._mcq(), "  1 ").score == 100.0

    def test_a_non_numeric_answer_is_wrong_not_an_error(self) -> None:
        """A student typing nonsense has answered incorrectly."""
        assert score_answer(self._mcq(), "banana").score == 0.0

    def test_an_empty_answer_is_wrong(self) -> None:
        assert score_answer(self._mcq(), "").score == 0.0

    def test_an_out_of_range_index_is_wrong(self) -> None:
        assert score_answer(self._mcq(), "99").score == 0.0

    def test_the_explanation_comes_back_as_feedback(self) -> None:
        assert score_answer(self._mcq(), "0").detail == "Square brackets build a list."

    def test_a_question_with_no_correct_option_cannot_be_marked(self) -> None:
        broken = _question(
            QuestionType.MULTIPLE_CHOICE, {"options": ["a", "b"], "explanation": "x"}
        )
        with pytest.raises(DomainRuleError):
            score_answer(broken, "0")

    def test_discrete_scoring_reports_no_test_fraction(self) -> None:
        scored = score_answer(self._mcq(), "1")
        assert scored.passed_tests is None
        assert scored.total_tests is None


class TestTrueFalse:
    def _tf(self, correct: bool = True) -> Question:
        return _question(
            QuestionType.TRUE_FALSE,
            {"prompt": "Lists are mutable.", "correct_answer": correct, "explanation": "Yes."},
        )

    @pytest.mark.parametrize("submitted", ["true", "True", " TRUE "])
    def test_matching_true_scores_full_marks(self, submitted: str) -> None:
        assert score_answer(self._tf(correct=True), submitted).score == 100.0

    def test_matching_false_scores_full_marks(self) -> None:
        assert score_answer(self._tf(correct=False), "false").score == 100.0

    def test_the_opposite_answer_scores_nothing(self) -> None:
        assert score_answer(self._tf(correct=True), "false").score == 0.0

    def test_anything_else_is_wrong_not_an_error(self) -> None:
        assert score_answer(self._tf(correct=True), "maybe").score == 0.0

    def test_a_question_with_no_answer_cannot_be_marked(self) -> None:
        with pytest.raises(DomainRuleError):
            score_answer(_question(QuestionType.TRUE_FALSE, {"explanation": "x"}), "true")


class TestOutputPrediction:
    def _op(self) -> Question:
        return _question(
            QuestionType.OUTPUT_PREDICTION,
            {
                "prompt": "What prints?",
                "code": "print(1)",
                "expected_output": "1",
                "explanation": "One.",
            },
        )

    def test_the_expected_output_scores_full_marks(self) -> None:
        assert score_answer(self._op(), "1").score == 100.0

    def test_a_trailing_newline_does_not_fail_a_correct_answer(self) -> None:
        """Compared the way the runner compares stdout."""
        assert score_answer(self._op(), "1\n").score == 100.0

    def test_windows_line_endings_do_not_fail_a_correct_answer(self) -> None:
        multiline = _question(
            QuestionType.OUTPUT_PREDICTION,
            {"expected_output": "a\nb", "explanation": "x"},
        )
        assert score_answer(multiline, "a\r\nb").score == 100.0

    def test_different_output_scores_nothing(self) -> None:
        assert score_answer(self._op(), "2").score == 0.0

    def test_internal_whitespace_still_matters(self) -> None:
        assert score_answer(self._op(), " 1").score == 0.0


class TestParsons:
    def _parsons(self) -> Question:
        return _question(
            QuestionType.PARSONS,
            {
                "prompt": "Order these.",
                "blocks": [
                    {"id": "a", "text": "def f():", "indent": 0},
                    {"id": "b", "text": "return 1", "indent": 1},
                ],
                "correct_order": ["a", "b"],
                "explanation": "Header first.",
            },
        )

    def test_the_correct_order_scores_full_marks(self) -> None:
        assert score_answer(self._parsons(), "a\nb").score == 100.0

    def test_comma_separated_ids_are_accepted(self) -> None:
        assert score_answer(self._parsons(), "a, b").score == 100.0

    def test_the_wrong_order_scores_nothing(self) -> None:
        assert score_answer(self._parsons(), "b\na").score == 0.0

    def test_a_missing_block_scores_nothing(self) -> None:
        assert score_answer(self._parsons(), "a").score == 0.0

    def test_blank_lines_are_ignored(self) -> None:
        assert score_answer(self._parsons(), "a\n\n\nb\n").score == 100.0

    def test_a_question_with_no_order_cannot_be_marked(self) -> None:
        with pytest.raises(DomainRuleError):
            score_answer(_question(QuestionType.PARSONS, {"explanation": "x"}), "a")


class TestExecutable:
    """The test fraction is the score. These run real subprocesses."""

    def _coding(self, *, in_content: bool = True) -> Question:
        content: dict = {"prompt": "Echo the input.", "reference_solution": "", "explanation": "x"}
        if in_content:
            content["tests"] = ECHO_CASES
            return _question(QuestionType.CODING, content, kind=QuestionKind.TESTABLE_PROGRAM)
        return _question(
            QuestionType.CODING,
            content,
            kind=QuestionKind.TESTABLE_PROGRAM,
            tests=json.dumps(ECHO_CASES),
        )

    def test_passing_every_case_scores_full_marks(self) -> None:
        scored = score_answer(self._coding(), "print(input())")
        assert scored.passed_tests == 2
        assert scored.total_tests == 2
        assert scored.score == 100.0

    def test_passing_half_the_cases_scores_half(self) -> None:
        """The fixed rule: passed_tests / total_tests * 100."""
        scored = score_answer(self._coding(), "input()\nprint(1)")
        assert scored.passed_tests == 1
        assert scored.total_tests == 2
        assert scored.score == 50.0

    def test_a_program_matching_nothing_scores_zero(self) -> None:
        scored = score_answer(self._coding(), "print(99)")
        assert scored.score == 0.0
        assert scored.passed_tests == 0

    def test_a_syntax_error_is_a_wrong_answer_not_a_crash(self) -> None:
        scored = score_answer(self._coding(), "def oops(:")
        assert scored.score == 0.0

    def test_an_empty_submission_scores_zero_without_running_anything(self) -> None:
        scored = score_answer(self._coding(), "   ")
        assert scored.score == 0.0
        assert scored.passed_tests == 0
        assert scored.total_tests == 2
        assert scored.detail == "No answer submitted."

    def test_tests_stored_as_json_text_are_read(self) -> None:
        """Older rows keep their cases in the ``tests`` column, not in content."""
        scored = score_answer(self._coding(in_content=False), "print(1)")
        assert scored.total_tests == 2

    def test_a_question_with_no_test_cases_cannot_be_marked(self) -> None:
        broken = _question(
            QuestionType.CODING,
            {"prompt": "x", "explanation": "x"},
            kind=QuestionKind.TESTABLE_PROGRAM,
        )
        with pytest.raises(DomainRuleError):
            score_answer(broken, "print(1)")

    def test_failing_evidence_is_returned_to_the_student(self) -> None:
        scored = score_answer(self._coding(), "print(99)")
        assert scored.detail


def test_a_question_with_no_type_cannot_be_scored() -> None:
    untyped = Question(id=1, prompt="A question.", question_type=None)
    with pytest.raises(DomainRuleError):
        score_answer(untyped, "anything")
