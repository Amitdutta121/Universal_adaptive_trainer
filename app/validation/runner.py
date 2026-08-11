"""Run executable question tests in a local subprocess.

This is a local research prototype. ``-I`` and a timeout reduce accident risk,
but are not a multi-tenant sandbox: generated code can still use the filesystem.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.generation.schemas import ExecutableTestCase

EVIDENCE_LIMIT = 800


def normalize_output(text: str) -> str:
    """Normalize line endings and remove at most one trailing newline."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.removesuffix("\n")


@dataclass(frozen=True)
class ScriptResult:
    """Captured result of one isolated Python subprocess."""

    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool


@dataclass(frozen=True)
class TestRunSummary:
    """Aggregate outcome for executable test cases."""

    results: tuple[ScriptResult, ...]
    passed_count: int
    total: int
    timed_out: bool
    evidence: str | None


class LocalCodeRunner:
    """Execute generated Python locally with a bounded subprocess lifetime."""

    def __init__(self, timeout_seconds: float | None = None) -> None:
        self._timeout_seconds = (
            get_settings().validation_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )

    def run_script(self, source: str, *, stdin: str = "") -> ScriptResult:
        """Run source in an isolated temporary directory."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            path = directory / "snippet.py"
            path.write_text(source, encoding="utf-8")
            try:
                completed = subprocess.run(
                    [sys.executable, "-I", str(path)],
                    cwd=directory,
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                    env=_minimal_environment(),
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                return ScriptResult(
                    stdout=_timeout_output(error.stdout),
                    stderr=_timeout_output(error.stderr),
                    exit_code=None,
                    timed_out=True,
                )
        return ScriptResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            timed_out=False,
        )

    def run_tests(self, source: str, cases: Sequence[ExecutableTestCase]) -> TestRunSummary:
        """Run source once per hybrid executable test case."""
        results: list[ScriptResult] = []
        failures: list[str] = []
        passed_count = 0

        for index, case in enumerate(cases, start=1):
            script = source + "\n" + (case.assert_code or "")
            result = self.run_script(script, stdin=case.stdin)
            results.append(result)
            if _case_passed(result, case):
                passed_count += 1
                continue
            failures.append(_failure_evidence(index, result, case))

        total = len(cases)
        return TestRunSummary(
            results=tuple(results),
            passed_count=passed_count,
            total=total,
            timed_out=any(result.timed_out for result in results),
            evidence=None if passed_count == total else "\n".join(failures)[:EVIDENCE_LIMIT],
        )


def _minimal_environment() -> dict[str, str]:
    """Return the explicitly permitted environment for child Python processes."""
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    if sys.platform == "win32":
        environment["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        environment["WINDIR"] = os.environ.get("WINDIR", "")
    return environment


def _timeout_output(output: str | bytes | None) -> str:
    """Convert a timeout's partially captured stream into text."""
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _case_passed(result: ScriptResult, case: ExecutableTestCase) -> bool:
    """Apply the hybrid exit status and optional stdout expectation."""
    return (
        not result.timed_out
        and result.exit_code == 0
        and (
            case.stdout is None or normalize_output(result.stdout) == normalize_output(case.stdout)
        )
    )


def _failure_evidence(index: int, result: ScriptResult, case: ExecutableTestCase) -> str:
    """Summarize the relevant details for one failed executable case."""
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
