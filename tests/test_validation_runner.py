"""Tests for local executable-question validation."""

from __future__ import annotations

from app.generation.schemas import ExecutableTestCase
from app.validation.runner import LocalCodeRunner, normalize_output


def test_normalize_output_strips_one_trailing_newline() -> None:
    assert normalize_output("3\r\n") == "3"
    assert normalize_output("a\n\n") == "a\n"


def test_run_script_captures_stdout() -> None:
    result = LocalCodeRunner(timeout_seconds=2).run_script("print(1 + 2)")
    assert result.timed_out is False
    assert result.exit_code == 0
    assert normalize_output(result.stdout) == "3"


def test_run_script_times_out() -> None:
    result = LocalCodeRunner(timeout_seconds=0.3).run_script("import time; time.sleep(5)")
    assert result.timed_out is True


def test_run_tests_stdout_and_assert() -> None:
    source = "def add(a, b):\n    return a + b\n"
    summary = LocalCodeRunner(timeout_seconds=2).run_tests(
        source,
        [
            ExecutableTestCase(stdin="", stdout=None, assert_code="assert add(1, 2) == 3"),
            ExecutableTestCase.model_validate({"stdin": "", "assert": "assert add(2, 2) == 4"}),
        ],
    )
    assert summary.passed_count == 2
    assert summary.total == 2
    assert summary.timed_out is False


def test_run_tests_reports_stdout_mismatch() -> None:
    summary = LocalCodeRunner(timeout_seconds=2).run_tests(
        "print(4)",
        [ExecutableTestCase(stdout="3")],
    )
    assert summary.passed_count == 0
    assert summary.total == 1
    assert summary.evidence
