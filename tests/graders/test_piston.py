"""PistonExecutor against a running Piston service (C7). Skipped when the service is not reachable.

Start it with ``docker compose -f docker/piston/docker-compose.yml up -d`` and install the python
runtime (``docker/piston/README.md``). ``PISTON_URL`` overrides the default http://127.0.0.1:2000.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from graders.executors.base import Executor, RunRequest, RunResult
from graders.executors.piston import PistonExecutor

BASE_URL = os.environ.get("PISTON_URL", "http://127.0.0.1:2000")
PYTHON_VERSION = "3.12.0"
#: Everything Isolate and the python runtime put in a job's environment (observed on 3.1.1).
SANDBOX_ENVIRONMENT = {
    "HOME",
    "LC_CTYPE",
    "LIBC_FATAL_STDERR_",
    "PATH",
    "PISTON_LANGUAGE",
    "PWD",
    "SHLVL",
    "_",
}


def _unavailable_reason() -> str | None:
    try:
        runtimes = httpx.get(f"{BASE_URL}/api/v2/runtimes", timeout=2.0).json()
    except (httpx.HTTPError, ValueError) as error:
        return f"Piston is not reachable at {BASE_URL} ({type(error).__name__}); see docker/piston"
    if not any(
        r.get("language") == "python" and r.get("version") == PYTHON_VERSION for r in runtimes
    ):
        return f"Piston at {BASE_URL} has no python {PYTHON_VERSION} runtime; see docker/piston"
    return None


_REASON = _unavailable_reason()
pytestmark = pytest.mark.skipif(_REASON is not None, reason=_REASON or "")


@pytest.fixture(scope="module")
def piston() -> Iterator[PistonExecutor]:
    executor = PistonExecutor(base_url=BASE_URL, python_version=PYTHON_VERSION)
    yield executor
    executor.close()


def run(executor: Executor, source: str, stdin: str = "", timeout_s: float = 5.0) -> RunResult:
    return executor.run(
        RunRequest(language="python", source=source, stdin=stdin, timeout_s=timeout_s)
    )


def _assert_healthy(piston: PistonExecutor) -> None:
    result = run(piston, "print('still alive')")
    assert result == RunResult("still alive\n", "", 0, False)


# --- normal programs -------------------------------------------------------------------------


def test_it_is_an_executor(piston: PistonExecutor) -> None:
    assert isinstance(piston, Executor)


def test_hello_world(piston: PistonExecutor) -> None:
    assert run(piston, "print('hello world')") == RunResult("hello world\n", "", 0, False)


def test_stdin_is_delivered_byte_for_byte(piston: PistonExecutor) -> None:
    echo = "import sys\nsys.stdout.write(repr(sys.stdin.read()))"
    assert run(piston, echo, stdin="a\nb").stdout == repr("a\nb")
    assert run(piston, echo, stdin="").stdout == repr("")
    assert run(piston, "print(input()[::-1])", stdin="abc\n").stdout == "cba\n"


def test_input_past_end_of_stdin_is_eof(piston: PistonExecutor) -> None:
    result = run(piston, "input()")
    assert result.exit_code == 1
    assert "EOFError" in result.stderr


def test_nonzero_exit_and_stderr(piston: PistonExecutor) -> None:
    result = run(piston, "import sys\nprint('out')\nprint('bad', file=sys.stderr)\nsys.exit(3)")
    assert result == RunResult("out\n", "bad\n", 3, False)


def test_assert_failure(piston: PistonExecutor) -> None:
    result = run(piston, "assert 1 + 1 == 3, 'math is broken'")
    assert result.exit_code == 1
    assert not result.timed_out
    assert result.stderr.startswith("Traceback (most recent call last):\n")
    assert "snippet.py" in result.stderr
    assert result.stderr.endswith("AssertionError: math is broken\n")
    assert "launcher" not in result.stderr


def test_program_sees_only_itself(piston: PistonExecutor) -> None:
    source = (
        "import os, sys\n"
        "print(sorted(os.listdir('.')), __name__,"
        " os.path.basename(__file__), os.path.basename(sys.argv[0]))"
    )
    assert run(piston, source).stdout == "['snippet.py'] __main__ snippet.py snippet.py\n"


def test_timeout(piston: PistonExecutor) -> None:
    result = run(piston, "print('started', flush=True)\nwhile True: pass", timeout_s=1)
    assert result.timed_out
    assert result.exit_code is None
    assert result.stdout == "started\n"


def test_sleeping_past_the_timeout_is_a_timeout(piston: PistonExecutor) -> None:
    result = run(piston, "import time\ntime.sleep(30)", timeout_s=1)
    assert (result.timed_out, result.exit_code) == (True, None)


def test_unsupported_language(piston: PistonExecutor) -> None:
    result = piston.run(RunRequest(language="ruby", source="puts 1"))
    assert result == RunResult("", result.stderr, None, False, result.stderr)  # an infra error
    assert "unsupported language 'ruby'" in result.stderr


def test_unreachable_service_is_a_result_not_an_exception() -> None:
    executor = PistonExecutor(base_url="http://127.0.0.1:9", request_slack_s=2)
    result = run(executor, "print(1)")
    assert (result.stdout, result.exit_code, result.timed_out) == ("", None, False)
    assert "Piston sandbox unreachable" in result.stderr


def test_rejected_request_is_a_result(piston: PistonExecutor) -> None:
    result = PistonExecutor(base_url=BASE_URL, python_version="0.0.1").run(
        RunRequest(language="python", source="print(1)")
    )
    assert result.exit_code is None
    assert "Piston rejected the run (HTTP 400)" in result.stderr
    assert "runtime is unknown" in result.stderr


# --- hostile programs: every one must be contained -------------------------------------------


def test_cannot_write_outside_the_box(piston: PistonExecutor) -> None:
    probe = (
        "import json\n"
        "results = {}\n"
        "for path in ['/etc/x', '/usr/x', '/bin/x', '/piston/packages/x',\n"
        "             '/piston/packages/python/3.12.0/bin/python3.12', '/x', '/proc/x']:\n"
        "    try:\n"
        "        with open(path, 'a') as handle:\n"
        "            handle.write('pwned')\n"
        "        results[path] = 'written'\n"
        "    except OSError as error:\n"
        "        results[path] = type(error).__name__\n"
        "print(json.dumps(results))\n"
    )
    result = run(piston, probe)
    assert result.exit_code == 0, result.stderr
    assert "written" not in json.loads(result.stdout).values()
    # The shared runtime is untouched: python still runs.
    _assert_healthy(piston)


def test_tmp_does_not_survive_between_runs(piston: PistonExecutor) -> None:
    write = "open('/tmp/marker', 'w').write('left behind'); print('ok')"
    assert run(piston, write).stdout == "ok\n"
    check = "import os; print(os.path.exists('/tmp/marker'))"
    assert run(piston, check).stdout == "False\n"


def test_network_is_unavailable(piston: PistonExecutor) -> None:
    probe = (
        "import socket, urllib.request\n"
        "attempts = {\n"
        "    'http': lambda: urllib.request.urlopen('http://example.com', timeout=3),\n"
        "    'ip': lambda: socket.create_connection(('1.1.1.1', 80), timeout=3),\n"
        "    'piston_api': lambda: socket.create_connection(('127.0.0.1', 2000), timeout=3),\n"
        "    'docker_host': lambda: socket.create_connection(\n"
        "        ('host.docker.internal', 80), timeout=3),\n"
        "}\n"
        "for name, attempt in attempts.items():\n"
        "    try:\n"
        "        attempt()\n"
        "        print(name, 'CONNECTED')\n"
        "    except OSError as error:\n"
        "        print(name, 'blocked', type(error).__name__)\n"
    )
    result = run(piston, probe, timeout_s=15)
    assert result.exit_code == 0, result.stderr
    assert "CONNECTED" not in result.stdout
    assert result.stdout.count("blocked") == 4


def test_fork_bomb_is_contained(piston: PistonExecutor) -> None:
    bomb = (
        "import os\nwhile True:\n    try:\n        os.fork()\n    except OSError:\n        pass\n"
    )
    result = run(piston, bomb, timeout_s=2)
    assert result.exit_code is None
    assert result.timed_out
    _assert_healthy(piston)


def test_process_count_is_capped(piston: PistonExecutor) -> None:
    spawn = (
        "import os, time\n"
        "count = 0\n"
        "try:\n"
        "    while count < 10_000:\n"
        "        if os.fork() == 0:\n"
        "            time.sleep(3)\n"
        "            os._exit(0)\n"
        "        count += 1\n"
        "except OSError:\n"
        "    pass\n"
        "print(count)\n"
    )
    result = run(piston, spawn, timeout_s=5)
    assert result.exit_code == 0, result.stderr
    assert int(result.stdout) < 100  # the compose file caps a job at 64 processes


def test_one_gigabyte_is_killed(piston: PistonExecutor) -> None:
    result = run(piston, "data = bytearray(1024 ** 3)\nprint(len(data))")
    assert result.stdout == ""
    assert result.exit_code is None
    assert not result.timed_out
    assert "memory limit" in result.stderr
    _assert_healthy(piston)


def test_growing_memory_is_killed(piston: PistonExecutor) -> None:
    grow = "chunks = []\nwhile True:\n    chunks.append(bytearray(10 * 1024 * 1024))"
    result = run(piston, grow)
    assert (result.exit_code, result.timed_out) == (None, False)
    assert "memory limit" in result.stderr


def test_output_flood_is_cut_off(piston: PistonExecutor) -> None:
    result = run(piston, "while True:\n    print('x' * 1000)")
    assert result.exit_code is None
    assert "output limit" in result.stderr


def test_host_environment_and_files_are_not_visible(piston: PistonExecutor) -> None:
    probe = (
        "import json, os\n"
        "readable = {}\n"
        "for path in ['/piston_api/src/config.js', '/proc/1/environ', '/proc/1/cmdline',\n"
        "             '/sys/fs/cgroup/cgroup.procs', '/mnt/c/Windows/win.ini',\n"
        "             '/run/desktop/mnt/host/c/Windows/win.ini', '/var/run/docker.sock']:\n"
        "    try:\n"
        "        open(path).read(1)\n"
        "        readable[path] = True\n"
        "    except OSError:\n"
        "        readable[path] = False\n"
        "print(json.dumps({'env': sorted(os.environ), 'readable': readable}))\n"
    )
    result = run(piston, probe)
    assert result.exit_code == 0, result.stderr
    seen = json.loads(result.stdout)
    assert not any(seen["readable"].values()), seen["readable"]
    # Only the sandbox's own variables: none of the API's configuration, none of this machine's.
    assert set(seen["env"]) <= SANDBOX_ENVIRONMENT, seen["env"]
    # Nothing the probes did reached this machine.
    assert not Path("/etc/x").exists() and not Path("/x").exists()


# --- parity with LocalExecutor ---------------------------------------------------------------

PARITY_CASES = [
    ("print('hello')", ""),
    ("name = input()\nprint(f'Hello, {name}!')", "Ada\n"),
    ("import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))", "1 2 3"),
    ("import sys\nprint(repr(sys.stdin.read()))", ""),
    ("input()", ""),
    ("def add(a, b):\n    return a + b\nassert add(2, 2) == 4\nprint('ok')", ""),
    ("def add(a, b):\n    return a - b\nassert add(2, 2) == 4, 'add is wrong'", ""),
    ("import sys\nprint('partial')\nsys.exit(2)", ""),
    ("print(", ""),
    ("raise ValueError('boom')", ""),
    ("if __name__ == '__main__':\n    print('main')", ""),
    ("print('é ✓ 日本')", ""),
]


@pytest.mark.parametrize(("source", "stdin"), PARITY_CASES, ids=range(len(PARITY_CASES)))
def test_same_result_as_local_executor(piston: PistonExecutor, source: str, stdin: str) -> None:
    local_module = pytest.importorskip("graders.executors.local")
    local = run(local_module.LocalExecutor(), source, stdin)
    sandboxed = run(piston, source, stdin)
    assert sandboxed.stdout == local.stdout
    assert sandboxed.exit_code == local.exit_code
    assert sandboxed.timed_out == local.timed_out
    # The last stderr line (the exception) matches; paths in the traceback differ by design.
    last = [result.stderr.strip().splitlines()[-1:] for result in (sandboxed, local)]
    assert last[0] == last[1]


def test_timeout_parity_with_local_executor(piston: PistonExecutor) -> None:
    local_module = pytest.importorskip("graders.executors.local")
    source = "while True: pass"
    local = run(local_module.LocalExecutor(), source, timeout_s=1)
    sandboxed = run(piston, source, timeout_s=1)
    assert (sandboxed.exit_code, sandboxed.timed_out) == (local.exit_code, local.timed_out)
