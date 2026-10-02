"""Python code graders: ``code.python.tests`` and ``code.python.execute`` (C2).

``code.python.tests`` is today's executable-question scoring
(``app/validation/runner.py::LocalCodeRunner.run_tests`` plus ``app/adaptive/scoring.py``),
moved: each hybrid stdin/stdout/assert case runs the student's source once, and the score is the
fraction of cases that pass. ``code.python.execute`` grades "what does this program print?".

Code never runs here directly; it goes through the :class:`~graders.executors.base.Executor`
the registry hands to :func:`build`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from graders.core import Grader, GradeResult, SpecError, SpecIssue, TestResult, parse_spec
from graders.executors.base import Executor, ExecutorError, RunRequest, RunResult

LANGUAGE = "python"
#: Feedback is cut to this many characters, as the app's runner always has.
EVIDENCE_LIMIT = 800
NO_ANSWER = "No answer submitted."
TIMED_OUT = "The submission did not finish in time."


def normalize_output(text: str) -> str:
    """Normalize line endings and remove at most one trailing newline."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.removesuffix("\n")


def run_python(
    executor: Executor, source: str, stdin: str = "", timeout_s: float = 5.0
) -> RunResult:
    """Run one Python program through ``executor`` (shared with the app's authoring checks).

    Raises:
        ExecutorError: the executor could not run it at all (e.g. the sandbox is down) -- never
            graded, because it says nothing about the program.
    """
    result = executor.run(
        RunRequest(language=LANGUAGE, source=source, stdin=stdin, timeout_s=timeout_s)
    )
    if result.infra_error is not None:
        raise ExecutorError(result.infra_error)
    return result


# --- specs -----------------------------------------------------------------------------------


class PythonTestCase(BaseModel):
    """One hybrid case: feed ``stdin``; pass on exit 0 and, if given, matching ``stdout``."""

    __test__ = False  # not a pytest test class
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    stdin: str = ""
    stdout: str | None = None
    assert_code: str | None = Field(default=None, alias="assert")

    @model_validator(mode="after")
    def _requires_stdout_or_assert(self) -> PythonTestCase:
        if self.stdout is None and self.assert_code is None:
            raise ValueError("each test needs stdout or assert")
        return self


class PythonTestsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tests: list[PythonTestCase] = Field(min_length=1)
    reference_solution: str | None = None
    timeout_s: float = Field(default=5.0, gt=0)


class PythonExecuteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    stdin: str = ""
    expected_stdout: str | None = None
    timeout_s: float = Field(default=5.0, gt=0)


def _spec_issues(model: type[BaseModel], spec: Mapping[str, Any]) -> list[SpecIssue]:
    """Structural problems with a raw spec, worded as issues instead of raised."""
    try:
        model.model_validate(dict(spec))
    except ValidationError as error:
        issues = []
        for problem in error.errors():
            location = ".".join(str(part) for part in problem["loc"]) or "spec"
            if problem["loc"] == ("tests",) and problem["type"] == "too_short":
                code = "no_tests"
            elif "needs stdout or assert" in problem["msg"]:
                code = "test_missing_expectation"
            else:
                code = "invalid_spec"
            issues.append(SpecIssue(code=code, message=f"{location}: {problem['msg']}"))
        return issues
    except TypeError as error:
        return [SpecIssue(code="invalid_spec", message=str(error))]
    return []


# --- code.python.tests ------------------------------------------------------------------------


@dataclass(frozen=True)
class SuiteOutcome:
    passed_count: int
    total: int
    timed_out: bool
    tests: tuple[TestResult, ...]
    #: One raw run per case, in order (the app's authoring checks inspect exit codes).
    results: tuple[RunResult, ...]
    #: Failure lines joined and capped, or ``None`` when every case passed.
    evidence: str | None


def _case_passed(result: RunResult, case: PythonTestCase) -> bool:
    return (
        not result.timed_out
        and result.exit_code == 0
        and (
            case.stdout is None or normalize_output(result.stdout) == normalize_output(case.stdout)
        )
    )


def _failure_evidence(index: int, result: RunResult, case: PythonTestCase) -> str:
    if result.timed_out:
        return f"Test {index}: timed out."
    if result.exit_code != 0:
        return f"Test {index}: exited with code {result.exit_code}. {result.stderr}".strip()
    if case.stdout is not None:
        return (
            f"Test {index}: stdout mismatch; expected {normalize_output(case.stdout)!r}, "
            f"got {normalize_output(result.stdout)!r}."
        )
    return f"Test {index}: failed."


def run_tests(
    executor: Executor, source: str, cases: list[PythonTestCase], timeout_s: float
) -> SuiteOutcome:
    """Run ``source`` once per hybrid case (the one implementation; the app's checks use it too).

    Raises:
        ExecutorError: see :func:`run_python`.
    """
    tests: list[TestResult] = []
    results: list[RunResult] = []
    failures: list[str] = []
    passed_count = 0
    timed_out = False
    for index, case in enumerate(cases, start=1):
        result = run_python(
            executor, source + "\n" + (case.assert_code or ""), case.stdin, timeout_s
        )
        results.append(result)
        timed_out = timed_out or result.timed_out
        passed = _case_passed(result, case)
        message = None
        if passed:
            passed_count += 1
        else:
            message = _failure_evidence(index, result, case)
            failures.append(message)
        tests.append(
            TestResult(
                name=f"Test {index}",
                passed=passed,
                points=1.0 if passed else 0.0,
                max_points=1.0,
                message=message,
            )
        )
    total = len(cases)
    return SuiteOutcome(
        passed_count=passed_count,
        total=total,
        timed_out=timed_out,
        tests=tuple(tests),
        results=tuple(results),
        evidence=None if passed_count == total else "\n".join(failures)[:EVIDENCE_LIMIT],
    )


def _run_suite(executor: Executor, source: str, spec: PythonTestsSpec) -> SuiteOutcome:
    return run_tests(executor, source, spec.tests, spec.timeout_s)


class PythonTestsGrader:
    """Run the student's source once per case; score = fraction of cases passed."""

    capability = "code.python.tests"
    version = "1"
    spec_model = PythonTestsSpec

    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]:
        issues = _spec_issues(PythonTestsSpec, spec)
        if issues:
            return issues
        parsed = PythonTestsSpec.model_validate(dict(spec))
        if parsed.reference_solution is None:
            return []
        outcome = _run_suite(self._executor, parsed.reference_solution, parsed)
        if outcome.passed_count == outcome.total:
            return []
        evidence = outcome.evidence or (TIMED_OUT if outcome.timed_out else "")
        return [
            SpecIssue(
                code="reference_fails_tests",
                message=(
                    f"The reference solution passes {outcome.passed_count} of {outcome.total} "
                    f"tests. {evidence}"
                ).strip(),
            )
        ]

    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult:
        parsed = cast(PythonTestsSpec, parse_spec(PythonTestsSpec, spec))
        if not answer.strip():
            # Nothing to run: every case fails without starting a process.
            return GradeResult(
                score=0.0,
                tests=tuple(
                    TestResult(
                        name=f"Test {index}", passed=False, points=0.0, max_points=1.0, message=None
                    )
                    for index in range(1, len(parsed.tests) + 1)
                ),
                feedback=NO_ANSWER,
            )
        outcome = _run_suite(self._executor, answer, parsed)
        feedback = outcome.evidence
        if outcome.timed_out and not feedback:
            feedback = TIMED_OUT
        return GradeResult(
            score=outcome.passed_count / outcome.total, tests=outcome.tests, feedback=feedback
        )


# --- code.python.execute ----------------------------------------------------------------------


def _run_problem(result: RunResult) -> SpecIssue | None:
    if result.timed_out:
        return SpecIssue(code="program_times_out", message="The program did not finish in time.")
    if result.exit_code != 0:
        return SpecIssue(
            code="program_fails",
            message=f"The program exited with code {result.exit_code}. {result.stderr}".strip(),
        )
    return None


class PythonExecuteGrader:
    """The answer is what the spec's program prints (compared after output normalization)."""

    capability = "code.python.execute"
    version = "1"
    spec_model = PythonExecuteSpec

    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def _run(self, spec: PythonExecuteSpec) -> RunResult:
        return run_python(self._executor, spec.source, spec.stdin, spec.timeout_s)

    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]:
        issues = _spec_issues(PythonExecuteSpec, spec)
        if issues:
            return issues
        parsed = PythonExecuteSpec.model_validate(dict(spec))
        result = self._run(parsed)
        problem = _run_problem(result)
        if problem is not None:
            return [problem]
        if parsed.expected_stdout is not None and normalize_output(
            result.stdout
        ) != normalize_output(parsed.expected_stdout):
            return [
                SpecIssue(
                    code="expected_output_wrong",
                    message=(
                        f"expected_stdout is {normalize_output(parsed.expected_stdout)!r} but the "
                        f"program prints {normalize_output(result.stdout)!r}."
                    ),
                )
            ]
        return []

    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult:
        parsed = cast(PythonExecuteSpec, parse_spec(PythonExecuteSpec, spec))
        expected = parsed.expected_stdout
        if expected is None:
            result = self._run(parsed)
            problem = _run_problem(result)
            if problem is not None:
                raise SpecError(problem.message)
            expected = result.stdout
        correct = normalize_output(answer) == normalize_output(expected)
        return GradeResult(score=1.0 if correct else 0.0)


def build(executor_factory: Callable[[], Executor]) -> list[Grader]:
    """Both Python graders, sharing one executor."""
    executor = executor_factory()
    return [PythonTestsGrader(executor), PythonExecuteGrader(executor)]


__all__ = [
    "PythonExecuteGrader",
    "PythonExecuteSpec",
    "PythonTestCase",
    "PythonTestsGrader",
    "PythonTestsSpec",
    "SuiteOutcome",
    "build",
    "normalize_output",
    "run_python",
    "run_tests",
]
