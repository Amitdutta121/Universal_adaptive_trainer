"""Helpers several question types share (moved from ``generation/prompts.py``,
``validation/type_checks.py`` and ``assessment/specs.py`` in T0a, unchanged)."""

from __future__ import annotations

import ast
import json
from typing import Any

from app.domain.questions import QuestionCheck
from app.generation.schemas import ExecutableTestCase
from app.validation.report import make_check
from app.validation.runner import (
    EVIDENCE_LIMIT,
    LocalCodeRunner,
    TestRunSummary,
    normalize_output,
    parse_test_cases,
)

#: How the validator runs the tests a draft declares. Stated for every executable
#: type because the model consistently got it wrong without it: it would write a
#: solution that only *defines* functions, then declare a ``stdout`` expectation
#: as though the function had been called and printed. Four of six hard debugging
#: questions failed that way; spelling out the contract took them to six of six,
#: with declared stdout cases falling from 14 to 1.
EXECUTABLE_CONTRACT = """
How your tests will be run:
* reference_solution is written to a file and executed as a whole program.
* For each test, its `assert` code is APPENDED to the end of your solution and
  runs after it, in the same scope.
* Its `stdin` is piped to the program as standard input. It is NOT executed as
  Python -- never put code in stdin.
* A test passes if the program exits cleanly and, when `stdout` is set, its
  printed output matches exactly.
So: if your solution only defines functions and prints nothing, leave `stdout`
unset and put every check in `assert`. Only set `stdout` if the program really
prints that text when run. Before answering, run your reference_solution against
every test in your head and confirm it does what you declared."""


# --- grading plans --------------------------------------------------------------------------


def explanation(content: dict) -> str | None:
    text = content.get("explanation")
    return text if isinstance(text, str) and text.strip() else None


def same(answer: str) -> str:
    return answer


def stored_case_specs(raw: object) -> list[dict[str, Any]] | None:
    """Stored test cases as grader spec entries, or ``None`` if unusable.

    Uses the app's own reader so "usable" means exactly what it meant before.
    """
    cases = parse_test_cases(raw)
    if cases is None:
        return None
    return [
        {"stdin": case.stdin, "stdout": case.stdout, "assert": case.assert_code} for case in cases
    ]


# --- legacy columns ---------------------------------------------------------------------------


def tests_json(tests: list[ExecutableTestCase]) -> str:
    return json.dumps([case.model_dump(mode="json", by_alias=True) for case in tests])


# --- authoring checks -------------------------------------------------------------------------


def parses(source: str) -> bool:
    try:
        ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return False
    return True


def parse_tests(raw: object) -> list[ExecutableTestCase] | None:
    return parse_test_cases(raw)


def present_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def run_reference(
    reference: object,
    reference_parses: bool,
    tests: list[ExecutableTestCase] | None,
    runner: LocalCodeRunner,
) -> TestRunSummary | None:
    if not reference_parses or tests is None:
        return None
    return runner.run_tests(reference, tests)


def reference_check(summary: TestRunSummary | None, total: int) -> QuestionCheck:
    passed = summary.passed_count if summary is not None else 0
    successful = summary is not None and passed == summary.total and not summary.timed_out
    evidence = summary.evidence if summary is not None else None
    return make_check(
        "reference_passes_tests",
        successful,
        f"{passed}/{total} tests pass",
        evidence,
    )


def script_evidence(result: object, expected: str) -> str:
    if result.timed_out:
        return "Execution timed out."
    if result.exit_code != 0:
        evidence = f"Exited with code {result.exit_code}. {result.stderr}".strip()
    else:
        evidence = (
            f"stdout mismatch; expected {normalize_output(expected)!r}, "
            f"got {normalize_output(result.stdout)!r}."
        )
    return evidence[:EVIDENCE_LIMIT]
