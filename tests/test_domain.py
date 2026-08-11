"""Foundational domain entities and the fixed adaptive-training rules."""

from __future__ import annotations

import pytest

from app.domain import (
    INITIAL_SUBTOPIC_WEAKNESS,
    MAX_SCORE,
    Difficulty,
    MasteryBand,
    Question,
    QuestionCheck,
    QuestionStatus,
    QuestionValidationReport,
    difficulty_for_mastery,
    mastery_band,
    score_from_tests,
)
from app.domain.questions import DEFAULT_PRIORITY, LOWEST_PRIORITY, apply_professor_edit


class TestScoring:
    """Student question scores range 0-100, from passed/total tests."""

    @pytest.mark.parametrize(
        ("passed", "total", "expected"),
        [(0, 10, 0.0), (5, 10, 50.0), (10, 10, 100.0), (1, 3, pytest.approx(33.3333, abs=1e-3))],
    )
    def test_score_from_tests(self, passed: int, total: int, expected: float) -> None:
        assert score_from_tests(passed, total) == expected

    def test_full_pass_is_the_maximum_score(self) -> None:
        assert score_from_tests(7, 7) == MAX_SCORE

    @pytest.mark.parametrize(("passed", "total"), [(0, 0), (-1, 5), (6, 5), (1, -2)])
    def test_invalid_test_counts_are_rejected(self, passed: int, total: int) -> None:
        with pytest.raises(ValueError):
            score_from_tests(passed, total)


class TestMasteryToDifficulty:
    """Fixed decision: low mastery -> easy, medium -> medium, high -> hard."""

    def test_low_mastery_gives_easy(self) -> None:
        assert mastery_band(0.05) is MasteryBand.LOW
        assert difficulty_for_mastery(0.05) is Difficulty.EASY

    def test_medium_mastery_gives_medium(self) -> None:
        assert mastery_band(0.55) is MasteryBand.MEDIUM
        assert difficulty_for_mastery(0.55) is Difficulty.MEDIUM

    def test_high_mastery_gives_hard(self) -> None:
        assert mastery_band(0.95) is MasteryBand.HIGH
        assert difficulty_for_mastery(0.95) is Difficulty.HARD

    def test_difficulty_is_monotonic_across_the_range(self) -> None:
        order = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]
        seen = [difficulty_for_mastery(p / 20) for p in range(21)]
        indices = [order.index(d) for d in seen]
        assert indices == sorted(indices)

    @pytest.mark.parametrize("p_known", [-0.01, 1.01, 5.0])
    def test_out_of_range_mastery_is_rejected(self, p_known: float) -> None:
        with pytest.raises(ValueError):
            difficulty_for_mastery(p_known)


def test_all_subtopic_weaknesses_start_equal() -> None:
    """Fixed decision: the first roulette draw must be uniform."""
    weaknesses = {f"subtopic-{i}": INITIAL_SUBTOPIC_WEAKNESS for i in range(5)}
    assert len(set(weaknesses.values())) == 1
    assert INITIAL_SUBTOPIC_WEAKNESS > 0


class TestQuestionOriginals:
    """Generated originals must survive professor edits."""

    def test_original_is_captured_on_creation(self) -> None:
        question = Question(prompt="Write a loop.", reference_solution="pass", tests="assert True")
        assert question.original_prompt == "Write a loop."
        assert question.original_reference_solution == "pass"
        assert question.original_tests == "assert True"
        assert question.was_edited_by_professor is False

    def test_edit_keeps_the_generated_original(self) -> None:
        question = Question(prompt="Write a loop.", reference_solution="pass")
        edited = apply_professor_edit(
            question, prompt="Write a for-loop over a list.", reference_solution="print(1)"
        )
        assert edited.prompt == "Write a for-loop over a list."
        assert edited.reference_solution == "print(1)"
        assert edited.original_prompt == "Write a loop."
        assert edited.original_reference_solution == "pass"
        assert edited.was_edited_by_professor is True
        # The source object is untouched.
        assert question.prompt == "Write a loop."

    def test_priority_constants_order_used_questions_last(self) -> None:
        assert LOWEST_PRIORITY < DEFAULT_PRIORITY

    def test_empty_prompt_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            Question(prompt="")


class TestValidationPrecedence:
    """Deterministic checks outrank LLM judgment."""

    def test_all_deterministic_checks_passing_passes(self) -> None:
        report = QuestionValidationReport(
            checks=[
                QuestionCheck(name="solution_parses", passed=True),
                QuestionCheck(name="solution_passes_own_tests", passed=True),
            ]
        )
        assert report.passed is True
        assert report.resulting_status() is QuestionStatus.VALIDATION_PASSED

    def test_a_failed_deterministic_check_cannot_be_overridden_by_an_llm(self) -> None:
        report = QuestionValidationReport(
            checks=[
                QuestionCheck(name="solution_parses", passed=False, deterministic=True),
                QuestionCheck(name="llm_thinks_it_is_great", passed=True, deterministic=False),
            ]
        )
        assert report.passed is False
        assert report.resulting_status() is QuestionStatus.VALIDATION_FAILED

    def test_llm_judgment_alone_does_not_pass_a_question(self) -> None:
        report = QuestionValidationReport(
            checks=[QuestionCheck(name="llm_review", passed=True, deterministic=False)]
        )
        assert report.passed is False

    def test_an_empty_report_does_not_pass(self) -> None:
        assert QuestionValidationReport().passed is False
