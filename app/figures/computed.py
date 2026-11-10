"""Run a computed-figure program for K seeds and check what it prints (ADR-080 point 3).

The program defines ``generate(seed)``. A harness wraps it, calls ``generate`` once with the seed
and the program prints ONE JSON object:
``{"prompt", "figure": {"svg", "alt", "caption"}, <the question type's draft fields>,
"explanation"}``. Each run goes through the configured executor with a short timeout and an
output cap; a run that times out, crashes, prints anything but one JSON object, or whose fields
fail the question type's own draft model is a problem, never a copy.

Pure functions: no LLM, no database, no file writes (the caller stores the SVGs). The program's
language and the import allowlist are the caller's (``app.generation.computed``), so nothing
here names one.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from graders.executors.base import Executor, ExecutorError, RunRequest

#: How much of a failed run's stderr is quoted back for the repair.
ERROR_EXCERPT_CHARS = 1500
#: Larger than any plot a question needs (real ones are 8-13 KB); same as the storage limit.
MAX_SVG_CHARS = 512 * 1024
#: Calls a program may not make: they touch files, other programs, the network or the clock.
FORBIDDEN_CALLS = frozenset(
    {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "exit", "quit"}
)
FORBIDDEN_ATTRIBUTES = frozenset({"sleep", "system", "popen", "unlink", "rmdir", "urlopen"})


@dataclass(frozen=True)
class RunLimits:
    #: The executor's language id for the program.
    language: str
    timeout_s: float
    max_output_bytes: int
    max_source_chars: int


@dataclass(frozen=True)
class ComputedCopy:
    """One checked copy: the type's draft fields (taxonomy excluded) plus its figure."""

    seed: int
    #: The draft fields as the type's ``draft_model`` validated them, without taxonomy ids.
    fields: dict[str, Any]
    svg: str
    alt: str
    caption: str


@dataclass(frozen=True)
class ProgramRun:
    copies: list[ComputedCopy] = field(default_factory=list)
    #: Why the program cannot be used, as sentences for the repair prompt. Empty when usable.
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def program_problems(source: str, *, allowed_modules: Collection[str], max_chars: int) -> list[str]:
    """Static checks before anything runs: size, syntax, ``generate``, imports and calls."""
    if len(source) > max_chars:
        return [f"the program is {len(source)} characters; the limit is {max_chars}"]
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [f"the program does not parse: line {error.lineno}: {error.msg}"]
    problems: list[str] = []
    if not any(isinstance(node, ast.FunctionDef) and node.name == "generate" for node in tree.body):
        problems.append("the program must define a top-level function generate(seed)")
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""] if node.level == 0 else ["."]
        for name in names:
            if name.split(".")[0] not in allowed_modules:
                problems.append(
                    f"the program imports {name!r}; only these modules are allowed: "
                    f"{', '.join(sorted(allowed_modules))}"
                )
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                problems.append(f"the program may not call {func.id}()")
            elif isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRIBUTES:
                problems.append(f"the program may not call .{func.attr}()")
    return list(dict.fromkeys(problems))


def harness(source: str, seed: int) -> str:
    """The program, wrapped to run once for ``seed``.

    The program runs as a module (not ``__main__``), with the global random generators seeded
    and matplotlib's SVG text kept as text. When ``generate`` returns a dict and prints nothing,
    the harness prints it as the one JSON line.
    """
    return f"""\
import contextlib as _contextlib, io as _io, json as _json, random as _random, sys as _sys
_random.seed({seed})
_namespace = {{"__name__": "figure_program"}}
exec(compile({source!r}, "program", "exec"), _namespace)
if "numpy" in _sys.modules:
    _sys.modules["numpy"].random.seed({seed})
if "matplotlib" in _sys.modules:
    _sys.modules["matplotlib"].rcParams["svg.fonttype"] = "none"
_buffer = _io.StringIO()
with _contextlib.redirect_stdout(_buffer):
    _result = _namespace["generate"]({seed})
_printed = _buffer.getvalue()
if not _printed.strip() and isinstance(_result, dict):
    _printed = _json.dumps(_result)
_sys.stdout.write(_printed)
"""


def _excerpt(text: str) -> str:
    text = text.strip()
    return text if len(text) <= ERROR_EXCERPT_CHARS else "..." + text[-ERROR_EXCERPT_CHARS:]


def run_once(
    source: str, seed: int, *, executor: Executor, limits: RunLimits
) -> tuple[dict[str, Any] | None, list[str]]:
    """Run the program for ``seed``: the JSON object it printed, or the problems.

    Raises:
        ExecutorError: the executor could not run it at all -- not the program's fault.
    """
    result = executor.run(
        RunRequest(
            language=limits.language, source=harness(source, seed), timeout_s=limits.timeout_s
        )
    )
    if result.infra_error:
        raise ExecutorError(result.infra_error)
    where = f"seed {seed}"
    if result.timed_out:
        return None, [
            f"{where}: the program did not finish within {limits.timeout_s:g} s; it must be "
            "fast: no sleeping, no large loops or simulations"
        ]
    size = len(result.stdout.encode("utf-8"))
    if size > limits.max_output_bytes:
        return None, [
            f"{where}: the program printed {size} bytes; the limit is {limits.max_output_bytes}"
            " (draw a smaller figure)"
        ]
    if result.exit_code != 0:
        return None, [f"{where}: the program crashed:\n{_excerpt(result.stderr)}"]
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        return None, [
            f"{where}: the program must print exactly one line (the JSON object); "
            f"it printed {len(lines)}"
        ]
    try:
        value = json.loads(lines[0])
    except json.JSONDecodeError as error:
        return None, [f"{where}: the printed line is not valid JSON ({error.msg})"]
    if not isinstance(value, dict):
        return None, [f"{where}: the printed JSON must be an object"]
    return value, []


def check_copy(
    raw: dict[str, Any],
    *,
    seed: int,
    draft_model: type[BaseModel],
    taxonomy: dict[str, Any],
) -> tuple[ComputedCopy | None, list[str]]:
    """Validate one printed object: its figure, and its fields as the type's draft model."""
    where = f"seed {seed}"
    problems: list[str] = []
    figure = raw.get("figure")
    svg = alt = caption = ""
    if not isinstance(figure, dict):
        problems.append(f'{where}: "figure" must be an object with "svg", "alt" and "caption"')
    else:
        svg, alt, caption = figure.get("svg"), figure.get("alt"), figure.get("caption", "")
        if not isinstance(svg, str) or not svg.lstrip()[:5].lower().startswith(("<svg", "<?xml")):
            problems.append(f'{where}: "figure.svg" must be the SVG document text')
        elif len(svg) > MAX_SVG_CHARS:
            problems.append(
                f"{where}: the SVG is {len(svg)} characters; the limit is {MAX_SVG_CHARS}"
            )
        elif "<script" in svg.lower():
            problems.append(f"{where}: the SVG may not contain a script")
        if not isinstance(alt, str) or not alt.strip():
            problems.append(f'{where}: "figure.alt" must describe the figure in words')
        if not isinstance(caption, str):
            problems.append(f'{where}: "figure.caption" must be text')
    taxonomy_keys = set(taxonomy)
    fields = {
        key: value for key, value in raw.items() if key != "figure" and key not in taxonomy_keys
    }
    try:
        draft = draft_model.model_validate({**fields, **taxonomy})
    except ValidationError as error:
        problems.extend(
            f"{where}: field '{'.'.join(str(part) for part in item['loc']) or '(object)'}': "
            f"{item['msg']}"
            for item in error.errors()
        )
        draft = None
    if problems or draft is None:
        return None, problems
    dumped = draft.model_dump(mode="json")
    for key in taxonomy_keys:
        dumped.pop(key, None)
    return ComputedCopy(seed=seed, fields=dumped, svg=svg, alt=alt, caption=caption), []


def run_program(
    source: str,
    *,
    seeds: Sequence[int],
    draft_model: type[BaseModel],
    taxonomy: dict[str, Any],
    executor: Executor,
    limits: RunLimits,
    allowed_modules: Collection[str],
) -> ProgramRun:
    """Check, run and validate the program for every seed. Usable only if every copy is.

    Stops at the first failing seed: one failure already means a repair, and a slow program
    should not be waited for K times.
    """
    static = program_problems(
        source, allowed_modules=allowed_modules, max_chars=limits.max_source_chars
    )
    if static:
        return ProgramRun(problems=static)
    copies: list[ComputedCopy] = []
    for seed in seeds:
        raw, problems = run_once(source, seed, executor=executor, limits=limits)
        if raw is not None:
            copy, problems = check_copy(raw, seed=seed, draft_model=draft_model, taxonomy=taxonomy)
            if copy is not None:
                copies.append(copy)
        if problems:
            return ProgramRun(copies=copies, problems=problems)
    if len(copies) > 1 and all(_same(copy, copies[0]) for copy in copies[1:]):
        return ProgramRun(
            copies=copies,
            problems=["every seed produced the same question; the numbers must depend on seed"],
        )
    return ProgramRun(copies=copies)


def _same(left: ComputedCopy, right: ComputedCopy) -> bool:
    return left.fields == right.fields and left.svg == right.svg


__all__ = [
    "ComputedCopy",
    "ProgramRun",
    "RunLimits",
    "check_copy",
    "harness",
    "program_problems",
    "run_once",
    "run_program",
]
