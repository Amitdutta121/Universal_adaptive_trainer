"""Run executable question tests for the authoring checks, through the isolated graders.

A thin shim (C5): running code and judging hybrid cases live in ``graders.python``, on the one
shared executor (``graders.get_executor``) -- local by default, which is NOT a sandbox, or Piston
when ``EXECUTOR=piston`` (C6). This module keeps the shapes :mod:`app.validation.type_checks`
uses and the shared test-case reader.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from app.config import get_settings
from app.errors import CodeExecutionUnavailableError
from app.generation.schemas import ExecutableTestCase
from graders import ExecutorError, get_executor
from graders.executors import RunResult
from graders.python import (
    EVIDENCE_LIMIT,
    PythonTestCase,
    normalize_output,
    run_python,
    run_tests,
)

#: One captured run: ``stdout``, ``stderr``, ``exit_code``, ``timed_out``.
ScriptResult = RunResult

__all__ = [
    "EVIDENCE_LIMIT",
    "LocalCodeRunner",
    "ScriptResult",
    "TestRunSummary",
    "normalize_output",
    "parse_test_cases",
]


def parse_test_cases(raw: object) -> list[ExecutableTestCase] | None:
    """Read stored test cases, from a decoded list or the JSON text of one.

    ``None`` means "these are not usable test cases" -- absent, empty, or not
    shaped like a case. Callers decide what that means: for validation it is a
    failing check, for scoring a student it is a question that cannot be marked.

    Lives here rather than in :mod:`app.validation.type_checks` so that reading a
    question's tests and running them are one import. It is what lets
    :mod:`app.adaptive` execute a student's answer without depending on
    :mod:`app.generation`.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if not isinstance(raw, list) or not raw:
        return None
    try:
        return [ExecutableTestCase.model_validate(case) for case in raw]
    except (ValidationError, TypeError):
        return None


@dataclass(frozen=True)
class TestRunSummary:
    """Aggregate outcome for executable test cases."""

    __test__ = False  # not a pytest test class

    results: tuple[ScriptResult, ...]
    passed_count: int
    total: int
    timed_out: bool
    evidence: str | None


def _unavailable(error: ExecutorError) -> CodeExecutionUnavailableError:
    return CodeExecutionUnavailableError(
        "Code could not be run right now, so this question could not be checked.",
        detail=str(error),
    )


class LocalCodeRunner:
    """Run generated Python through the graders' shared executor with a bounded run time.

    Raises :class:`~app.errors.CodeExecutionUnavailableError` when the executor cannot run code
    at all, so an outage is never reported as a failing check.
    """

    def __init__(self, timeout_seconds: float | None = None) -> None:
        self._timeout_seconds = (
            get_settings().validation_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )

    def run_script(self, source: str, *, stdin: str = "") -> ScriptResult:
        try:
            return run_python(get_executor(), source, stdin, self._timeout_seconds)
        except ExecutorError as error:
            raise _unavailable(error) from error

    def run_tests(self, source: str, cases: Sequence[ExecutableTestCase]) -> TestRunSummary:
        """Run source once per hybrid executable test case."""
        grader_cases = [
            PythonTestCase(stdin=case.stdin, stdout=case.stdout, assert_code=case.assert_code)
            for case in cases
        ]
        try:
            outcome = run_tests(get_executor(), source, grader_cases, self._timeout_seconds)
        except ExecutorError as error:
            raise _unavailable(error) from error
        return TestRunSummary(
            results=outcome.results,
            passed_count=outcome.passed_count,
            total=outcome.total,
            timed_out=outcome.timed_out,
            evidence=outcome.evidence,
        )
