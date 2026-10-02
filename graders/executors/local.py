"""Run code in a local subprocess -- ``app/validation/runner.py::LocalCodeRunner``, moved.

WARNING: this is NOT a sandbox. ``-I``, a minimal environment, a temporary working directory
and a timeout reduce accident risk, but submitted code can still read and write the filesystem,
open network connections and spawn processes. Use ``PistonExecutor`` for untrusted code.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from graders.executors.base import RunRequest, RunResult


class LocalExecutor:
    """Execute Python on this machine with a bounded subprocess lifetime."""

    def run(self, request: RunRequest) -> RunResult:
        if request.language != "python":
            return RunResult(
                stdout="",
                stderr=f"unsupported language {request.language!r}; LocalExecutor runs python only",
                exit_code=None,
                timed_out=False,
                infra_error=f"LocalExecutor runs python only, not {request.language!r}",
            )
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            path = directory / "snippet.py"
            path.write_text(request.source, encoding="utf-8")
            try:
                completed = subprocess.run(
                    [sys.executable, "-I", "-X", "utf8", str(path)],
                    cwd=directory,
                    input=request.stdin,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=request.timeout_s,
                    env=_minimal_environment(),
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                return RunResult(
                    stdout=_timeout_output(error.stdout),
                    stderr=_timeout_output(error.stderr),
                    exit_code=None,
                    timed_out=True,
                )
        return RunResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            timed_out=False,
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


__all__ = ["LocalExecutor"]
