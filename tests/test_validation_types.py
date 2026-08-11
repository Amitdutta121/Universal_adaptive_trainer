"""Tests for deterministic checks specific to each question type."""

from __future__ import annotations

import json

import pytest

from app.domain.enums import QuestionType
from app.domain.questions import Question
from app.validation.runner import LocalCodeRunner
from app.validation.type_checks import check_type, load_content

RUNNER = LocalCodeRunner(timeout_seconds=2)


def _question(question_type: QuestionType | None, content: object) -> Question:
    return Question(
        prompt="Validate this question.",
        question_type=question_type,
        content_json=json.dumps(content),
    )


def _checks(question_type: QuestionType, content: dict[str, object]) -> dict[str, object]:
    question = _question(question_type, content)
    return {check.name: check for check in check_type(question, content, RUNNER)}


@pytest.mark.parametrize(
    ("question_type", "content", "failed_check"),
    [
        (
            QuestionType.MULTIPLE_CHOICE,
            {"options": ["same", "same"], "correct_option_index": 0, "explanation": "Why."},
            "mc_no_duplicate_options",
        ),
        (
            QuestionType.MULTIPLE_CHOICE,
            {"options": ["one", "two"], "correct_option_index": 9, "explanation": "Why."},
            "mc_correct_option_exists",
        ),
        (
            QuestionType.TRUE_FALSE,
            {"correct_answer": "yes", "explanation": "Why."},
            "tf_boolean_answer",
        ),
        (
            QuestionType.TRUE_FALSE,
            {"correct_answer": True, "explanation": " "},
            "tf_explanation_present",
        ),
        (
            QuestionType.OUTPUT_PREDICTION,
            {"code": "def (", "expected_output": "3"},
            "output_code_parses",
        ),
        (
            QuestionType.OUTPUT_PREDICTION,
            {"code": "print(4)", "expected_output": "3"},
            "expected_output_verified",
        ),
        (
            QuestionType.CODE_COMPLETION,
            {"reference_solution": "print(1)", "tests": [{}]},
            "harness_valid",
        ),
        (
            QuestionType.CODE_COMPLETION,
            {
                "reference_solution": "def (",
                "tests": [{"assert": "assert True"}],
            },
            "completion_reference_parses",
        ),
        (
            QuestionType.DEBUGGING,
            {
                "code": "print(3)",
                "reference_solution": "print(3)",
                "tests": [{"stdout": "3"}],
            },
            "debug_broken_exhibits_issue",
        ),
        (
            QuestionType.DEBUGGING,
            {
                "code": "print(1)",
                "reference_solution": "print(1)",
                "tests": [{"stdout": "2"}],
            },
            "reference_passes_tests",
        ),
        (
            QuestionType.PARSONS,
            {
                "blocks": [
                    {"id": "a", "text": "x = 1", "indent": 0},
                    {"id": "b", "text": "print(x)", "indent": 0},
                ],
                "correct_order": ["a"],
            },
            "parsons_order_consistent",
        ),
        (
            QuestionType.PARSONS,
            {
                "blocks": [{"id": "a", "text": "print(3)", "indent": -1}],
                "correct_order": ["a"],
            },
            "parsons_indent_valid",
        ),
        (
            QuestionType.CODING,
            {
                "reference_solution": "print(1)",
                "tests": [{"stdout": "2"}],
            },
            "reference_passes_tests",
        ),
    ],
)
def test_invalid_fixture_fails_named_check(
    question_type: QuestionType,
    content: dict[str, object],
    failed_check: str,
) -> None:
    assert _checks(question_type, content)[failed_check].passed is False


def test_parsons_non_string_order_id_fails_consistency_check() -> None:
    content = {
        "blocks": [{"id": "only", "text": "print(3)", "indent": 0}],
        "correct_order": [{}],
    }
    question = _question(QuestionType.PARSONS, content)
    checks = {
        check.name: check
        for check in check_type(question, json.loads(question.content_json), RUNNER)
    }

    assert checks["parsons_order_consistent"].passed is False


@pytest.mark.parametrize(
    ("question_type", "content", "expected_names", "expected_details"),
    [
        (
            QuestionType.MULTIPLE_CHOICE,
            {"options": ["one", "two"], "correct_option_index": 0, "explanation": "Why."},
            [
                "mc_options_valid",
                "mc_no_duplicate_options",
                "mc_correct_option_exists",
                "mc_explanation_present",
            ],
            [
                "Options are valid",
                "No duplicate options",
                "Correct-answer reference exists",
                "Explanation exists",
            ],
        ),
        (
            QuestionType.TRUE_FALSE,
            {"correct_answer": True, "explanation": "Why."},
            ["tf_boolean_answer", "tf_explanation_present"],
            ["Valid boolean answer", "Explanation exists"],
        ),
        (
            QuestionType.OUTPUT_PREDICTION,
            {"code": "print(3)", "expected_output": "3"},
            ["output_code_parses", "expected_output_verified"],
            ["Prediction code parses", "Expected output verified"],
        ),
        (
            QuestionType.CODE_COMPLETION,
            {
                "reference_solution": "def add(a,b):\n    return a+b",
                "tests": [{"assert": "assert add(1,2)==3"}],
            },
            ["completion_reference_parses", "harness_valid", "reference_passes_tests"],
            ["Reference solution parses", "Test harness is valid", "1/1 tests pass"],
        ),
        (
            QuestionType.DEBUGGING,
            {
                "code": "print(1)",
                "reference_solution": "print(2)",
                "tests": [{"stdout": "2"}],
            },
            [
                "debug_broken_exhibits_issue",
                "debug_reference_parses",
                "harness_valid",
                "reference_passes_tests",
            ],
            [
                "Broken code exhibits the issue",
                "Reference solution parses",
                "Test harness is valid",
                "1/1 tests pass",
            ],
        ),
        (
            QuestionType.PARSONS,
            {
                "blocks": [{"id": "only", "text": "print(3)", "indent": 0}],
                "correct_order": ["only"],
            },
            [
                "parsons_order_consistent",
                "parsons_indent_valid",
                "parsons_reference_compiles",
            ],
            [
                "Canonical order is consistent",
                "Indentation representation is valid",
                "Reconstructed reference compiles",
            ],
        ),
        (
            QuestionType.CODING,
            {
                "reference_solution": "def add(a,b):\n    return a+b",
                "tests": [{"assert": "assert add(1,2)==3"}],
            },
            ["coding_reference_parses", "harness_valid", "reference_passes_tests"],
            ["Reference solution parses", "Test harness is valid", "1/1 tests pass"],
        ),
    ],
)
def test_happy_path_passes_all_type_checks(
    question_type: QuestionType,
    content: dict[str, object],
    expected_names: list[str],
    expected_details: list[str],
) -> None:
    checks = check_type(_question(question_type, content), content, RUNNER)

    assert [check.name for check in checks] == expected_names
    assert [check.detail for check in checks] == expected_details
    assert all(check.passed for check in checks)


@pytest.mark.parametrize("content_json", [None, "", "{", "[]"])
def test_load_content_returns_none_for_unreadable_content(content_json: str | None) -> None:
    question = Question(prompt="x", content_json=content_json)

    assert load_content(question) is None


def test_load_content_returns_decoded_object() -> None:
    question = Question(prompt="x", content_json='{"answer": 3}')

    assert load_content(question) == {"answer": 3}


def test_null_question_type_has_no_type_checks() -> None:
    question = _question(None, {})

    assert check_type(question, {}, RUNNER) == []
