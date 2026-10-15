"""The ``python_trace`` tool (Phase 5, Task 20)."""

from __future__ import annotations

import time

from app.tutorials.tools.python_trace import TraceResult, python_trace
from app.validation.runner import LocalCodeRunner


def _lines(result: TraceResult) -> list[tuple[int, str]]:
    return [(step.line, step.event) for step in result.steps]


def test_a_loop_is_traced_line_by_line_with_state_before_each_line() -> None:
    result = python_trace("total = 0\nfor i in range(3):\n    total += i\n    print(total)\n")
    assert result.ok and not result.truncated
    assert result.stdout == "0\n1\n3\n"
    assert _lines(result) == [
        (1, "line"),
        *[(2, "line"), (3, "line"), (4, "line")] * 3,
        (2, "line"),
        (2, "end"),  # the loop ends on its own line
    ]
    # Step 6 is the second pass over line 4: total was just updated to 1, "0" printed so far.
    assert result.steps[6].locals == {"total": "1", "i": "1"}
    assert result.steps[6].stdout == "0\n"
    assert result.steps[-1].locals == {"total": "3", "i": "2"}
    assert result.steps[-1].stdout == "0\n1\n3\n"


def test_a_function_call_records_call_body_and_return_value() -> None:
    result = python_trace("def square(x):\n    return x * x\n\ny = square(3)\n")
    assert _lines(result) == [
        (1, "line"),
        (4, "line"),
        (1, "call"),
        (2, "line"),
        (2, "return"),
        (4, "end"),
    ]
    call, body, ret = result.steps[2:5]
    assert call.function == body.function == "square"
    assert call.locals == {"x": "3"}
    assert ret.value == "9"
    assert result.steps[-1].locals == {"square": "<function square>", "y": "9"}


def test_an_uncaught_exception_is_recorded_and_reported() -> None:
    result = python_trace("x = 1\ny = x / 0\nprint('never')\n")
    assert result.error == "ZeroDivisionError: division by zero"
    assert not result.truncated
    exception = next(step for step in result.steps if step.event == "exception")
    assert (exception.line, exception.value) == (2, "ZeroDivisionError: division by zero")
    assert result.stdout == ""


def test_a_caught_exception_is_traced_and_the_run_finishes() -> None:
    code = "try:\n    int('x')\nexcept ValueError:\n    print('bad')\n"
    result = python_trace(code)
    assert result.ok
    assert result.stdout == "bad\n"
    assert any(step.event == "exception" and step.line == 2 for step in result.steps)


def test_an_infinite_loop_hits_the_step_cap_and_returns_an_error() -> None:
    started = time.monotonic()
    result = python_trace("n = 0\nwhile True:\n    n += 1\n", max_steps=100)
    assert time.monotonic() - started < 10
    assert result.truncated
    assert result.error is not None and "100 steps" in result.error
    assert len(result.steps) == 100


def test_a_loop_the_tracer_cannot_stop_hits_the_time_limit() -> None:
    # A bare ``except`` swallows the step cap; the executor's time limit still ends the run.
    code = "while True:\n    try:\n        pass\n    except:\n        pass\n"
    result = python_trace(code, max_steps=5, runner=LocalCodeRunner(timeout_seconds=2))
    assert result.truncated
    assert result.error is not None


def test_a_syntax_error_is_reported_without_steps() -> None:
    result = python_trace("x = (\n")
    assert result.steps == []
    assert result.error is not None and result.error.startswith("SyntaxError")


def test_stdin_is_fed_to_input() -> None:
    result = python_trace("name = input()\nprint('hi', name)\n", stdin="Ada\n")
    assert result.stdout == "hi Ada\n"
    assert result.steps[-1].locals == {"name": "'Ada'"}
