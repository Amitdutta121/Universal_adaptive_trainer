"""Run code inside a Piston sandbox (https://github.com/engineer-man/piston) over its HTTP API.

Piston runs each job in an Isolate box: its own mount, PID and network namespaces, a cgroup with
memory / process / CPU limits, an unprivileged uid, and a read-only view of everything except the
job's own directory. Start the service with ``docker/piston/docker-compose.yml`` (see the README
there). This is the executor for untrusted code; ``LocalExecutor`` is not a sandbox.

Behaviour matches ``LocalExecutor`` for normal programs: the program is ``snippet.py`` run as
``__main__`` from its own directory, stdin is delivered byte-for-byte, and an uncaught exception
prints the usual traceback and exits 1. ``run`` never raises: an unsupported language, an
unreachable service, a rejected request or a Piston internal error comes back as a
``RunResult`` with ``infra_error`` set (the reason is also in ``stderr``).

What the API returns, observed on Piston 3.1.1 (the ``run`` object of ``POST /api/v2/execute``):

- wall-clock or CPU timeout: ``status "TO"``, ``signal "SIGKILL"``, ``code null``;
- memory limit (cgroup OOM kill): ``status "RE"``, ``code 137``, ``signal null``, ``memory`` at
  the limit, and the runtime's wrapper script prints ``... Killed  python3.12 "$@"`` on stderr;
- stdout/stderr over the server's ``output_max_size``: ``status "OL"`` / ``"EL"``, ``SIGKILL``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from graders.executors.base import RunRequest, RunResult

#: The submitted program's file name, as in ``LocalExecutor``.
PROGRAM_NAME = "snippet.py"
_STDIN_NAME = ".stdin"
_LAUNCHER_NAME = "__piston_launcher__.py"

#: Piston always appends a newline to the request's stdin, so stdin is shipped as a file and put
#: on fd 0 by this launcher, which then runs the program as ``__main__`` and drops its own frame
#: from tracebacks. It removes its helper files first, so the program sees only ``snippet.py``.
_LAUNCHER = f"""\
import os as _os, sys as _sys, types as _types
_fd = _os.open({_STDIN_NAME!r}, _os.O_RDONLY)
_os.dup2(_fd, 0)
_os.close(_fd)
for _name in ({_STDIN_NAME!r}, {_LAUNCHER_NAME!r}):
    try:
        _os.unlink(_name)
    except OSError:
        pass
_path = _os.path.abspath({PROGRAM_NAME!r})
with open(_path, encoding="utf-8") as _file:
    _source = _file.read()
_main = _types.ModuleType("__main__")
_main.__file__ = _path
_main.__builtins__ = __builtins__
_sys.modules["__main__"] = _main
_sys.argv = [_path]
try:
    exec(compile(_source, _path, "exec"), _main.__dict__)
except SystemExit:
    raise
except BaseException as _error:
    _tb = None if isinstance(_error, SyntaxError) else _error.__traceback__.tb_next
    _sys.excepthook(type(_error), _error.with_traceback(_tb), _tb)
    raise SystemExit(1)
"""

#: Exit status of a process killed by SIGKILL, as reported through the runtime's shell wrapper.
_SIGKILL_EXIT = 137


class PistonExecutor:
    """Execute Python in a Piston sandbox reached over HTTP."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:2000",
        python_version: str = "3.12.0",
        memory_limit_bytes: int = 256 * 1024 * 1024,
        client: httpx.Client | None = None,
        *,
        request_slack_s: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.python_version = python_version
        self.memory_limit_bytes = memory_limit_bytes
        #: Extra HTTP time beyond the run timeout, for queueing and box setup.
        self.request_slack_s = request_slack_s
        self._client = client or httpx.Client()

    def run(self, request: RunRequest) -> RunResult:
        if request.language != "python":
            return _failure(
                f"unsupported language {request.language!r}; PistonExecutor runs python only"
            )
        # Piston ignores a limit of 0 (falls back to its default), so never send less than 1 ms.
        timeout_ms = max(1, round(request.timeout_s * 1000))
        payload = {
            "language": "python",
            "version": self.python_version,
            "files": [
                {"name": _LAUNCHER_NAME, "content": _LAUNCHER},
                {"name": PROGRAM_NAME, "content": request.source},
                {"name": _STDIN_NAME, "content": request.stdin},
            ],
            "stdin": "",
            "run_timeout": timeout_ms,
            "run_cpu_time": timeout_ms,
            "run_memory_limit": self.memory_limit_bytes,
        }
        url = f"{self.base_url}/api/v2/execute"
        try:
            response = self._client.post(
                url, json=payload, timeout=request.timeout_s + self.request_slack_s
            )
        except httpx.HTTPError as error:
            return _failure(f"Piston sandbox unreachable at {self.base_url}: {error!r}")
        try:
            body: Any = response.json()
        except json.JSONDecodeError:
            body = None
        if response.status_code != 200 or not isinstance(body, dict):
            message = body.get("message") if isinstance(body, dict) else response.text[:500]
            return _failure(f"Piston rejected the run (HTTP {response.status_code}): {message}")
        run = body.get("run")
        if not isinstance(run, dict):
            return _failure(f"Piston returned no run result: {str(body)[:500]}")
        return self._result(run)

    def _result(self, run: dict[str, Any]) -> RunResult:
        stdout = run.get("stdout") or ""
        stderr = run.get("stderr") or ""
        status = run.get("status")
        code = run.get("code")
        if status == "TO":
            return RunResult(stdout=stdout, stderr=stderr, exit_code=None, timed_out=True)
        if status in ("OL", "EL"):
            stream = "stdout" if status == "OL" else "stderr"
            note = f"killed: {stream} exceeded the sandbox output limit"
            return RunResult(stdout, _append(stderr, note), exit_code=None, timed_out=False)
        memory = run.get("memory")
        if (
            code == _SIGKILL_EXIT
            and isinstance(memory, int | float)
            and memory >= 0.9 * self.memory_limit_bytes
        ):
            limit_mib = self.memory_limit_bytes / (1024 * 1024)
            note = f"MemoryError: killed, the program exceeded the {limit_mib:g} MiB memory limit"
            return RunResult(stdout, _append(stderr, note), exit_code=None, timed_out=False)
        if status == "XX":
            return _failure(f"Piston internal error: {run.get('message')}")
        exit_code = code if isinstance(code, int) else None
        return RunResult(stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=False)

    def close(self) -> None:
        self._client.close()


def _append(stderr: str, note: str) -> str:
    if stderr and not stderr.endswith("\n"):
        stderr += "\n"
    return f"{stderr}{note}\n"


def _failure(message: str) -> RunResult:
    """The sandbox could not run the program: an infrastructure failure, not a wrong answer."""
    return RunResult(
        stdout="", stderr=message, exit_code=None, timed_out=False, infra_error=message
    )


__all__ = ["PROGRAM_NAME", "PistonExecutor"]
