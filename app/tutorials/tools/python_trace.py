"""``python_trace``: record what a Python snippet really does, step by step (Task 20).

The snippet runs inside a small tracer program on the graders' shared executor (through
:class:`~app.validation.runner.LocalCodeRunner`, like every authoring check), so it gets the same
isolation and time limit as any generated code. ``sys.settrace`` follows only the snippet's own
frames and records one step per event:

- ``line``: line ``line`` is about to run; ``locals`` and ``stdout`` are the state before it.
- ``call`` / ``return``: entering / leaving a function; ``value`` is the returned value.
- ``exception``: an exception passes through ``line``; ``value`` is ``"Type: message"``.
- ``end``: the snippet has finished (or been stopped by an exception); the final state.

Values are ``repr`` strings, cut to :data:`VALUE_CHARS`. A run that reaches ``max_steps`` stops
with an error (an infinite loop never hangs the caller); a run past the time limit is reported
the same way. A tutorial embeds these steps as-is: their truth comes from running the code, never
from a model.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.validation.runner import LocalCodeRunner

#: Steps recorded before a run is stopped. A stepper a student clicks through is far shorter.
DEFAULT_MAX_STEPS = 500
#: Characters kept of one value's ``repr`` and of the output so far.
VALUE_CHARS = 200
STDOUT_CHARS = 4000

_MARKER = "__PYTHON_TRACE__"

#: The tracer program. ``{source}``, ``{stdin}``, ``{max_steps}`` are ``repr``/int literals.
_TRACER = r"""
import io, json, sys, types

_SOURCE = {source}
_MAX_STEPS = {max_steps}
_steps = []
_out = io.StringIO()
_state = {{"capped": False}}


class _StepCap(BaseException):
    pass


def _value(v):
    if isinstance(v, (types.FunctionType, types.BuiltinFunctionType)):
        return "<function " + v.__name__ + ">"
    if isinstance(v, type):
        return "<class " + v.__name__ + ">"
    if isinstance(v, types.ModuleType):
        return "<module " + v.__name__ + ">"
    try:
        r = repr(v)
    except Exception:
        r = "<unprintable " + type(v).__name__ + ">"
    return r if len(r) <= {value_chars} else r[: {value_chars} - 3] + "..."


def _locals(frame):
    return {{k: _value(v) for k, v in frame.f_locals.items() if not k.startswith("__")}}


def _record(frame, event, value=None):
    if len(_steps) >= _MAX_STEPS:
        _state["capped"] = True
        raise _StepCap()
    step = {{
        "line": frame.f_lineno,
        "event": event,
        "function": frame.f_code.co_name,
        "locals": _locals(frame),
        "stdout": _out.getvalue()[-{stdout_chars}:],
    }}
    if value is not None:
        step["value"] = value
    _steps.append(step)


def _tracer(frame, event, arg):
    if frame.f_code.co_filename != "<snippet>":
        return None
    if event == "call":
        if frame.f_code.co_name != "<module>":
            _record(frame, "call")
    elif event == "line":
        _record(frame, "line")
    elif event == "return":
        if frame.f_code.co_name == "<module>":
            _record(frame, "end")
        else:
            _record(frame, "return", _value(arg))
    elif event == "exception" and not issubclass(arg[0], _StepCap):
        _record(frame, "exception", arg[0].__name__ + ": " + str(arg[1]))
    return _tracer


sys.stdin = io.StringIO({stdin})
_error = None
_real_stdout = sys.stdout
sys.stdout = _out
try:
    _code = compile(_SOURCE, "<snippet>", "exec")
    sys.settrace(_tracer)
    try:
        exec(_code, {{"__name__": "__main__"}})
    finally:
        sys.settrace(None)
except _StepCap:
    pass
except SyntaxError as e:
    _error = "SyntaxError: " + str(e.msg) + " (line " + str(e.lineno) + ")"
except BaseException as e:
    _error = type(e).__name__ + ": " + str(e)
finally:
    sys.stdout = _real_stdout
if _state["capped"]:
    _error = "Stopped after " + str(_MAX_STEPS) + " steps: the code may never finish."
print("{marker}" + json.dumps(
    {{"steps": _steps, "stdout": _out.getvalue()[-{stdout_chars}:], "error": _error,
      "truncated": _state["capped"]}}
))
"""


class TraceStep(BaseModel):
    line: int
    event: str
    function: str
    locals: dict[str, str] = Field(default_factory=dict)
    #: Everything printed before this step.
    stdout: str = ""
    #: ``return``: the returned value; ``exception``: ``"Type: message"``.
    value: str | None = None


class TraceResult(BaseModel):
    steps: list[TraceStep]
    #: Everything the snippet printed.
    stdout: str = ""
    #: Why the run did not finish normally: an uncaught exception, a syntax error, the step
    #: cap or the time limit. ``None`` for a clean run.
    error: str | None = None
    #: The step cap or the time limit stopped the run.
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None


def tracer_program(code: str, *, stdin: str = "", max_steps: int = DEFAULT_MAX_STEPS) -> str:
    """The program the executor runs to trace ``code``."""
    return _TRACER.format(
        source=repr(code),
        stdin=repr(stdin),
        max_steps=int(max_steps),
        value_chars=VALUE_CHARS,
        stdout_chars=STDOUT_CHARS,
        marker=_MARKER,
    )


def python_trace(
    code: str,
    *,
    stdin: str = "",
    max_steps: int = DEFAULT_MAX_STEPS,
    runner: LocalCodeRunner | None = None,
) -> TraceResult:
    """Run ``code`` and return its recorded steps.

    Raises :class:`~app.errors.CodeExecutionUnavailableError` when code cannot run at all
    (the executor is down): that says nothing about the snippet.
    """
    result = (runner or LocalCodeRunner()).run_script(
        tracer_program(code, stdin=stdin, max_steps=max_steps)
    )
    if result.timed_out:
        return TraceResult(
            steps=[], error="Stopped at the time limit: the code may never finish.", truncated=True
        )
    for line in reversed(result.stdout.splitlines()):
        if line.startswith(_MARKER):
            return TraceResult.model_validate(json.loads(line[len(_MARKER) :]))
    detail = (result.stderr or result.stdout).strip()[-VALUE_CHARS:]
    return TraceResult(steps=[], error=f"The tracer did not finish: {detail or 'no output'}")
