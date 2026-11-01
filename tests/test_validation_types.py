"""Tests for deterministic checks specific to each question type."""

from __future__ import annotations

import pytest

from app.domain.enums import QuestionType
from app.domain.questions import Question
from app.validation.runner import EVIDENCE_LIMIT, LocalCodeRunner
from app.validation.type_checks import check_type

RUNNER = LocalCodeRunner(timeout_seconds=2)


def _question(question_type: QuestionType | None, content: dict[str, object]) -> Question:
    return Question(
        prompt="Validate this question.",
        question_type=question_type,
        content=content,
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
    checks = {check.name: check for check in check_type(question, content, RUNNER)}

    assert checks["parsons_order_consistent"].passed is False


def test_output_prediction_mismatch_evidence_is_bounded() -> None:
    content = {
        "code": f"print({'x' * (EVIDENCE_LIMIT * 2)!r})",
        "expected_output": "short",
    }

    evidence = _checks(QuestionType.OUTPUT_PREDICTION, content)["expected_output_verified"].evidence

    assert evidence is not None
    assert len(evidence) <= EVIDENCE_LIMIT


@pytest.mark.parametrize(
    ("question_type", "content", "expected_names", "expected_details"),
    [
        (
            QuestionType.MULTIPLE_CHOICE,
            {"options": ["one", "two"], "correct_option_index": 0, "explanation": "Why."},
            ["mc_no_duplicate_options", "mc_explanation_present"],
            ["No duplicate options", "Explanation exists"],
        ),
        (
            QuestionType.TRUE_FALSE,
            {"correct_answer": True, "explanation": "Why."},
            ["tf_explanation_present"],
            ["Explanation exists"],
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
                "code": "def add(a,b):\n    return ___",
                "reference_solution": "def add(a,b):\n    return a+b",
                "tests": [{"assert": "assert add(1,2)==3"}],
            },
            ["completion_reference_parses", "completion_stub_incomplete"],
            ["Reference solution parses", "Starter code leaves something to complete"],
        ),
        (
            QuestionType.DEBUGGING,
            {
                "code": "print(1)",
                "reference_solution": "print(2)",
                "tests": [{"stdout": "2"}],
            },
            ["debug_broken_exhibits_issue", "debug_reference_parses"],
            ["Broken code exhibits the issue", "Reference solution parses"],
        ),
        (
            QuestionType.PARSONS,
            {
                "blocks": [{"id": "only", "text": "print(3)", "indent": 0}],
                "correct_order": ["only"],
            },
            ["parsons_order_consistent", "parsons_reference_compiles"],
            ["Canonical order uses every block once", "Reconstructed reference compiles"],
        ),
        (
            QuestionType.CODING,
            {
                "reference_solution": "def add(a,b):\n    return a+b",
                "tests": [{"assert": "assert add(1,2)==3"}],
            },
            ["coding_reference_parses"],
            ["Reference solution parses"],
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


def test_null_question_type_has_no_type_checks() -> None:
    question = _question(None, {})

    assert check_type(question, {}, RUNNER) == []


ADD = "def add(a, b):\n    return a + b"


@pytest.mark.parametrize(
    "stub",
    [
        ADD,  # the live case: the stub shown was the full solution
        "def add(a, b):\n    # TODO: nothing left to do\n    return a + b",  # same code
        "def add(a, b):\n    return a - b",  # no blank to complete
        None,
    ],
)
def test_a_completion_stub_that_is_the_solution_or_has_no_blank_fails(stub: str | None) -> None:
    content: dict[str, object] = {
        "reference_solution": ADD,
        "tests": [{"assert": "assert add(1, 2) == 3"}],
    }
    if stub is not None:
        content["code"] = stub
    check = _checks(QuestionType.CODE_COMPLETION, content)["completion_stub_incomplete"]
    assert check.passed is False
    assert check.evidence


@pytest.mark.parametrize(
    "stub",
    [
        "def add(a, b):\n    return ___",
        "def add(a, b):\n    ...",
        "def add(a, b):\n    pass",
        "def add(a, b):\n    # TODO: return the sum\n    return None",
    ],
)
def test_a_completion_stub_with_a_blank_passes(stub: str) -> None:
    content = {"code": stub, "reference_solution": ADD, "tests": [{"assert": "assert True"}]}
    assert _checks(QuestionType.CODE_COMPLETION, content)["completion_stub_incomplete"].passed


def test_an_unclosed_code_fence_in_the_prompt_fails_and_a_closed_one_passes() -> None:
    from app.validation.shared import check_shared

    def fence(prompt: str):
        question = Question(prompt=prompt, question_type=QuestionType.MULTIPLE_CHOICE)
        checks = {check.name: check for check in check_shared(question, None)}
        return checks.get("prompt_code_fences_closed")

    assert fence("What does this print?\n```python\nprint(1)\n").passed is False
    assert fence("What does this print?\n```python\nprint(1)\n```").passed is True
    assert fence("What does print(1) show?") is None


def test_a_broken_stub_fails_the_attempt_and_is_retried() -> None:
    """The validator runs inside the retry loop, so the failed check becomes a correction."""
    from app.generation.attempts import _check_instructions
    from app.validation.service import DeterministicQuestionValidator

    question = Question(
        prompt="Finish add.\n```python\ndef add(a, b):",
        question_type=QuestionType.CODE_COMPLETION,
        content={
            "code": ADD,
            "reference_solution": ADD,
            "tests": [{"assert": "assert add(1, 2) == 3"}],
        },
    )
    report = DeterministicQuestionValidator().validate(question)
    failed = [check for check in report.checks if not check.passed]
    names = {check.name for check in failed}
    assert {"completion_stub_incomplete", "prompt_code_fences_closed"} <= names
    assert not report.passed
    corrections = " ".join(_check_instructions(failed))
    assert "leave a visible blank" in corrections
    assert "Close every ``` code block" in corrections
