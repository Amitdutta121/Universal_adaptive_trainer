"""C2: the Python graders and LocalExecutor."""

from __future__ import annotations

import re

import pytest

import graders
from graders import SpecError
from graders.executors.base import Executor, RunRequest, RunResult
from graders.executors.local import LocalExecutor
from graders.python import (
    EVIDENCE_LIMIT,
    PythonExecuteGrader,
    PythonTestsGrader,
    build,
    normalize_output,
    run_python,
)

ADD = "def add(a, b):\n    return a + b\n"


@pytest.fixture(scope="module")
def executor() -> LocalExecutor:
    return LocalExecutor()


@pytest.fixture(scope="module")
def tests_grader(executor: LocalExecutor) -> PythonTestsGrader:
    return PythonTestsGrader(executor)


@pytest.fixture(scope="module")
def execute_grader(executor: LocalExecutor) -> PythonExecuteGrader:
    return PythonExecuteGrader(executor)


class _CountingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, request: RunRequest) -> RunResult:
        self.calls += 1
        return RunResult(stdout="", stderr="", exit_code=0, timed_out=False)


# --- LocalExecutor ----------------------------------------------------------------------------


def test_local_executor_captures_stdout_stdin_and_unicode(executor: LocalExecutor) -> None:
    assert isinstance(executor, Executor)
    result = executor.run(
        RunRequest(language="python", source='print(input() + " café")', stdin="hi\n")
    )
    assert result == RunResult(stdout="hi café\n", stderr="", exit_code=0, timed_out=False)


def test_local_executor_times_out(executor: LocalExecutor) -> None:
    result = run_python(executor, "while True: pass", timeout_s=1)
    assert result.timed_out is True
    assert result.exit_code is None


def test_local_executor_reports_a_crash(executor: LocalExecutor) -> None:
    result = run_python(executor, "raise ValueError('boom')")
    assert result.exit_code == 1
    assert "ValueError: boom" in result.stderr
    assert result.timed_out is False


def test_local_executor_rejects_other_languages(executor: LocalExecutor) -> None:
    result = executor.run(RunRequest(language="javascript", source="console.log(1)"))
    assert result.exit_code is None
    assert result.timed_out is False
    assert result.stdout == ""
    assert "unsupported language" in result.stderr
    assert result.infra_error is not None


# --- code.python.tests: grade -----------------------------------------------------------------


def test_all_cases_pass(tests_grader: PythonTestsGrader) -> None:
    spec = {
        "tests": [
            {"assert": "assert add(1, 2) == 3"},
            {"stdin": "", "assert": "assert add(2, 2) == 4"},
        ]
    }
    result = tests_grader.grade(spec, ADD)
    assert result.score == 1.0
    assert result.feedback is None
    assert [t.passed for t in result.tests] == [True, True]
    assert result.tests[0].name == "Test 1"
    assert result.tests[0].points == 1 and result.tests[0].max_points == 1
    assert result.tests[0].message is None


def test_partial_credit_two_of_three(tests_grader: PythonTestsGrader) -> None:
    spec = {
        "tests": [
            {"assert": "assert add(1, 2) == 3"},
            {"assert": "assert add(1, 1) == 3"},
            {"assert": "assert add(0, 0) == 0"},
        ]
    }
    result = tests_grader.grade(spec, ADD)
    assert result.score == pytest.approx(2 / 3)
    assert [t.passed for t in result.tests] == [True, False, True]
    assert result.tests[1].points == 0
    assert result.feedback is not None
    assert result.feedback.startswith("Test 2: exited with code 1.")
    assert "AssertionError" in result.feedback
    assert result.tests[1].message == result.feedback


def test_stdout_only_cases_with_stdin(tests_grader: PythonTestsGrader) -> None:
    spec = {"tests": [{"stdin": "4\n", "stdout": "8\r\n"}, {"stdin": "5\n", "stdout": "11"}]}
    result = tests_grader.grade(spec, "print(int(input()) * 2)")
    assert result.score == 0.5
    assert result.feedback == "Test 2: stdout mismatch; expected '11', got '10'."


def test_failing_suite(tests_grader: PythonTestsGrader) -> None:
    result = tests_grader.grade({"tests": [{"stdout": "3"}]}, "print(4)")
    assert result.score == 0.0
    assert result.feedback == "Test 1: stdout mismatch; expected '3', got '4'."


def test_crash_is_a_wrong_answer(tests_grader: PythonTestsGrader) -> None:
    result = tests_grader.grade({"tests": [{"stdout": "1"}]}, "def broken(:\n")
    assert result.score == 0.0
    assert result.format_error is None
    assert result.feedback is not None
    assert result.feedback.startswith("Test 1: exited with code 1.")
    assert "SyntaxError" in result.feedback


def test_timeout(tests_grader: PythonTestsGrader) -> None:
    spec = {"tests": [{"stdout": "1"}], "timeout_s": 1}
    result = tests_grader.grade(spec, "while True: pass")
    assert result.score == 0.0
    assert result.feedback == "Test 1: timed out."
    assert result.tests[0].message == "Test 1: timed out."


def test_empty_answer_runs_nothing() -> None:
    counting = _CountingExecutor()
    result = PythonTestsGrader(counting).grade(
        {"tests": [{"stdout": "1"}, {"assert": "pass"}]}, "  \n\t"
    )
    assert counting.calls == 0
    assert result.score == 0.0
    assert result.feedback == "No answer submitted."
    assert [t.passed for t in result.tests] == [False, False]


def test_stdout_mismatch_on_empty_output() -> None:
    result = PythonTestsGrader(_CountingExecutor()).grade({"tests": [{"stdout": "x"}]}, "x")
    assert result.feedback == "Test 1: stdout mismatch; expected 'x', got ''."


def test_feedback_is_capped_at_800_chars(tests_grader: PythonTestsGrader) -> None:
    spec = {"tests": [{"stdout": "y" * 300} for _ in range(4)]}
    result = tests_grader.grade(spec, "print('x' * 300)")
    assert result.score == 0.0
    assert result.feedback is not None
    assert len(result.feedback) == EVIDENCE_LIMIT
    assert result.feedback.startswith("Test 1: stdout mismatch; expected 'yyy")
    # each test keeps its own full message
    assert len(result.tests[3].message or "") > 600


def test_malformed_spec_raises(tests_grader: PythonTestsGrader) -> None:
    with pytest.raises(SpecError):
        tests_grader.grade({"tests": []}, ADD)
    with pytest.raises(SpecError):
        tests_grader.grade({"tests": [{"stdout": "1"}], "unknown": 1}, ADD)


# --- code.python.tests: check_spec ------------------------------------------------------------


def test_check_spec_structural_issues(tests_grader: PythonTestsGrader) -> None:
    assert [i.code for i in tests_grader.check_spec({"tests": []})] == ["no_tests"]
    assert [i.code for i in tests_grader.check_spec({})] == ["invalid_spec"]
    issues = tests_grader.check_spec({"tests": [{"stdin": "1"}]})
    assert [i.code for i in issues] == ["test_missing_expectation"]


def test_check_spec_without_reference_runs_nothing() -> None:
    counting = _CountingExecutor()
    assert PythonTestsGrader(counting).check_spec({"tests": [{"stdout": "1"}]}) == []
    assert counting.calls == 0


def test_check_spec_reference_solution(tests_grader: PythonTestsGrader) -> None:
    tests = [{"assert": "assert add(1, 2) == 3"}, {"assert": "assert add(2, 2) == 4"}]
    assert tests_grader.check_spec({"tests": tests, "reference_solution": ADD}) == []

    wrong = "def add(a, b):\n    return a * b\n"
    issues = tests_grader.check_spec({"tests": tests, "reference_solution": wrong})
    assert [i.code for i in issues] == ["reference_fails_tests"]
    assert "1 of 2" in issues[0].message
    assert "Test 1: exited with code 1." in issues[0].message


# --- code.python.execute ----------------------------------------------------------------------


def test_execute_with_expected_stdout(execute_grader: PythonExecuteGrader) -> None:
    spec = {"source": "print(sum(range(4)))", "expected_stdout": "6\n"}
    assert execute_grader.check_spec(spec) == []
    assert execute_grader.grade(spec, "6").score == 1.0
    assert execute_grader.grade(spec, "6\r\n").score == 1.0
    assert execute_grader.grade(spec, "7").score == 0.0


def test_execute_without_expected_stdout_runs_the_program(
    execute_grader: PythonExecuteGrader,
) -> None:
    spec = {"source": "x = input()\nprint(x[::-1])\nprint(len(x))", "stdin": "abc\n"}
    assert execute_grader.check_spec(spec) == []
    assert execute_grader.grade(spec, "cba\n3").score == 1.0
    assert execute_grader.grade(spec, "cba").score == 0.0


def test_execute_check_spec_issues(execute_grader: PythonExecuteGrader) -> None:
    wrong = {"source": "print(1)", "expected_stdout": "2"}
    assert [i.code for i in execute_grader.check_spec(wrong)] == ["expected_output_wrong"]
    fails = {"source": "1/0"}
    issues = execute_grader.check_spec(fails)
    assert [i.code for i in issues] == ["program_fails"]
    assert "ZeroDivisionError" in issues[0].message
    slow = {"source": "while True: pass", "timeout_s": 1}
    assert [i.code for i in execute_grader.check_spec(slow)] == ["program_times_out"]
    assert [i.code for i in execute_grader.check_spec({})] == ["invalid_spec"]


def test_execute_grade_raises_when_program_fails(execute_grader: PythonExecuteGrader) -> None:
    with pytest.raises(SpecError):
        execute_grader.grade({"source": "raise SystemExit(3)"}, "anything")


# --- registry ---------------------------------------------------------------------------------


def test_build_shares_one_executor() -> None:
    made: list[_CountingExecutor] = []

    def factory() -> _CountingExecutor:
        made.append(_CountingExecutor())
        return made[-1]

    built = build(factory)
    assert {g.capability for g in built} == {"code.python.tests", "code.python.execute"}
    assert len(made) == 1
    assert all(isinstance(g, graders.Grader) for g in built)


def test_registry_default_executor_is_local() -> None:
    graders.set_executor(None)
    try:
        grader = graders.get_grader("code.python.tests")
        assert grader.capability == "code.python.tests"
        assert grader.grade({"tests": [{"stdout": "3"}]}, "print(1 + 2)").score == 1.0
        assert graders.get_grader("code.python.execute").version == "1"
    finally:
        graders.set_executor(None)


def test_normalize_output() -> None:
    assert normalize_output("3\r\n") == "3"
    assert normalize_output("a\n\n") == "a\n"
    assert normalize_output("a\rb") == "a\nb"


# --- parity with the frozen pre-move runner ------------------------------------------------

PARITY_CASES = [
    (ADD, [{"assert": "assert add(1, 2) == 3"}, {"assert": "assert add(2, 2) == 4"}]),
    ("print(4)", [{"stdout": "3"}]),
    ("print(int(input()) + 1)", [{"stdin": "1\n", "stdout": "2"}, {"stdin": "5", "stdout": "7"}]),
    (
        ADD,
        [
            {"assert": "assert add(1, 2) == 3"},
            {"assert": "assert add(1, 1) == 3"},
            {"stdout": "", "assert": "print(add(2, 3))"},
        ],
    ),
    ("def broken(:\n", [{"stdout": "1"}]),
    ("import sys\nsys.exit(2)", [{"assert": "pass"}]),
]


@pytest.mark.parametrize(("source", "cases"), PARITY_CASES)
def test_parity_with_the_frozen_runner(
    tests_grader: PythonTestsGrader, source: str, cases: list[dict]
) -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from frozen_runner import LocalCodeRunner

    from app.generation.schemas import ExecutableTestCase

    summary = LocalCodeRunner(timeout_seconds=5).run_tests(
        source, [ExecutableTestCase.model_validate(case) for case in cases]
    )
    result = tests_grader.grade({"tests": cases}, source)

    assert sum(t.passed for t in result.tests) == summary.passed_count
    assert len(result.tests) == summary.total
    assert result.score == summary.passed_count / summary.total
    # stderr tracebacks name each run's own temporary directory; everything else must match.
    assert _without_temp_dirs(result.feedback) == _without_temp_dirs(summary.evidence)


def _without_temp_dirs(text: str | None) -> str | None:
    return None if text is None else re.sub(r"tmp[\w-]+", "tmp", text)
