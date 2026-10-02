"""The executor contract (C0). Frozen.

Graders that run code never call ``subprocess`` themselves; they are handed an
:class:`Executor`. ``LocalExecutor`` (C2) runs on this machine and is **not a sandbox**;
``PistonExecutor`` (C7) runs inside an isolated container. Both return the same
:class:`RunResult`, so a grader cannot tell them apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RunRequest:
    #: Language id, e.g. ``"python"``.
    language: str
    source: str
    stdin: str = ""
    timeout_s: float = 5.0


@dataclass(frozen=True)
class RunResult:
    stdout: str
    stderr: str
    #: ``None`` when the run did not finish (timed out, killed, or never started).
    exit_code: int | None
    timed_out: bool
    #: Set when the executor could not run the program at all -- the sandbox is unreachable or
    #: rejected the request, or the language is unsupported. Not the program's fault, so it must
    #: never be graded as a wrong answer (graders raise :class:`ExecutorError` instead).
    infra_error: str | None = None


class ExecutorError(Exception):
    """Code could not be run for a reason outside the submission (``RunResult.infra_error``)."""


@runtime_checkable
class Executor(Protocol):
    def run(self, request: RunRequest) -> RunResult: ...
