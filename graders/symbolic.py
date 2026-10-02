"""``symbolic.expression_equivalence``: is the student's expression (or equation) equivalent to the
expected one? (track C, work package C4)

Spec: ``expected`` (e.g. ``"2*x*sin(x) + x**2*cos(x)"``), the ``variables`` a student may use,
optionally ``allowed_functions`` (a subset of :data:`SAFE_NAMES`), ``equation`` mode, the numeric
sample count and tolerance, and an ``explanation`` returned as feedback on every grade.

Answer convention: plain math text. ``2x``, ``x^2`` and ``sin x`` are accepted (implicit
multiplication / application, ``^`` as power); a run of declared single-letter variables such as
``xy`` reads as ``x*y``. In equation mode the answer is ``lhs = rhs``.

**Safe parsing.** ``sympy.parsing`` ends in ``eval``, so untrusted text is screened before it gets
there, and the ``eval`` itself sees nothing dangerous:

1. Text checks: at most :data:`MAX_ANSWER_LENGTH` characters, no ``__``, only ASCII letters,
   digits, ``_``, spaces/tabs/newlines and ``+-*/^().,=`` (``_`` is allowed so variables such as
   ``v_0`` can be typed; ``__`` is still refused).
2. Token checks (Python's tokenizer): every name is a declared variable, a whitelisted
   function/constant, or a run of declared single-letter variables; numbers are plain decimals
   (no ``0x``, no ``2j``); no ``.`` operator (so no attribute access at all).
3. ``parse_expr`` runs with a ``local_dict`` of only those variables (plain ``Symbol``) and
   functions, and a ``global_dict`` of only the sympy constructors the transformations emit
   (``Integer``, ``Float``, ``Rational``, ``Symbol``, ``Add``, ``Mul``, ``Pow``) with
   ``__builtins__`` emptied, so a name that slipped through could not reach Python builtins.
4. Size check: the text is first parsed *unevaluated* and every power's exponent is bounded
   (:data:`MAX_EXPONENT`, and the product along nested powers by :data:`MAX_EXPONENT_PRODUCT`), so
   ``9^9^9`` is refused instead of computed. Only then is it parsed evaluated.
5. The result must be a sympy expression whose free symbols are all declared.

Any failure is a ``format_error`` (score 0) for an answer, a :class:`SpecError` for ``expected``.

**Equivalence.** ``simplify(answer - expected) == 0`` (equation mode: ``simplify(A/E)`` is a
nonzero constant, where ``A``/``E`` are ``lhs - rhs`` of answer/expected, so ``2y = 4x`` matches
``y = 2x``), run under a time budget. If simplify does not prove it (or runs out of time) a
randomized numeric check decides: both sides are evaluated at deterministic pseudo-random points
with every variable in [-3, 3]; points where either side is not finite and real are skipped and
replaced, up to ``4 * numeric_samples`` draws. The answer is correct when at least half of
``numeric_samples`` points were usable and every usable point agrees within
``tolerance * max(1, |expected|)`` (equation mode: all ratios ``A/E`` agree and are nonzero).
Simplify can only prove equivalence, never refute it -- the numeric check is what marks wrong.

Known limit: time budgets use a daemon thread, which cannot be killed; a pathological expression
that blows the budget keeps computing in the background until it finishes. The input limits
above keep that rare.
"""

from __future__ import annotations

import io
import keyword
import math
import random
import re
import threading
import tokenize
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import sympy
from pydantic import BaseModel, ConfigDict, Field
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from graders.core import Grader, GradeResult, SpecError, SpecIssue, parse_spec
from graders.executors.base import Executor

CAPABILITY = "symbolic.expression_equivalence"

MAX_ANSWER_LENGTH = 300
MAX_EXPONENT = 100
MAX_EXPONENT_PRODUCT = 1000
SIMPLIFY_BUDGET_S = 3.0
NUMERIC_BUDGET_S = 5.0
SAMPLE_RANGE = (-3.0, 3.0)

#: Every function/constant a spec may whitelist, by the name students type.
SAFE_NAMES: dict[str, Any] = {
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "asin": sympy.asin,
    "acos": sympy.acos,
    "atan": sympy.atan,
    "sinh": sympy.sinh,
    "cosh": sympy.cosh,
    "tanh": sympy.tanh,
    "exp": sympy.exp,
    "log": sympy.log,
    "ln": sympy.log,
    "sqrt": sympy.sqrt,
    "abs": sympy.Abs,
    "pi": sympy.pi,
    "E": sympy.E,
}

#: The only globals the generated code can see.
_GLOBALS: dict[str, Any] = {
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    "Rational": sympy.Rational,
    "Symbol": sympy.Symbol,
    "Add": sympy.Add,
    "Mul": sympy.Mul,
    "Pow": sympy.Pow,
}

_TRANSFORMATIONS = (*standard_transformations, implicit_multiplication_application, convert_xor)
_ALLOWED_CHARS = re.compile(r"[A-Za-z0-9_ \t\r\n+\-*/^().,=]*")
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_DECIMAL = re.compile(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")


class SymbolicSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)
    allowed_functions: list[str] | None = None
    equation: bool = False
    numeric_samples: int = 12
    tolerance: float = Field(default=1e-9, gt=0)
    explanation: str | None = None


class _ParseError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class _Context:
    symbols: dict[str, sympy.Symbol]
    functions: dict[str, Any]
    equation: bool

    def local_dict(self) -> dict[str, Any]:
        return {**self.functions, **self.symbols}


# --- safe parsing ---------------------------------------------------------------------------


def _check_names(text: str, context: _Context) -> None:
    single_letters = {name for name in context.symbols if len(name) == 1}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError) as error:
        raise _ParseError("syntax", "The expression could not be read.") from error
    for token in tokens:
        if token.type == tokenize.NAME:
            name = token.string
            if name in context.symbols or name in context.functions:
                continue
            if name.isalpha() and set(name) <= single_letters:
                continue  # "xy" -> x*y, as sympy's split_symbols does
            raise _ParseError(
                "unknown_name", f"'{name}' is not a variable or function this question accepts."
            )
        elif token.type == tokenize.NUMBER:
            if not _DECIMAL.fullmatch(token.string):
                raise _ParseError("syntax", f"'{token.string}' is not a plain number.")
        elif token.type == tokenize.OP and token.string == ".":
            raise _ParseError("syntax", "A '.' may only appear inside a number.")
        elif token.type == tokenize.ERRORTOKEN and token.string.strip():
            raise _ParseError("syntax", "The expression could not be read.")


def _bound_powers(node: sympy.Basic, factor: float = 1.0) -> None:
    """Refuse unevaluated trees whose powers would be huge to compute (``9^9^9``)."""
    if isinstance(node, sympy.Pow):
        base, exponent = node.args
        if not exponent.free_symbols:
            _bound_powers(exponent, factor)
            try:
                size = abs(complex(exponent.evalf(15)))
            except (TypeError, ValueError, OverflowError):
                size = math.inf
            if size > MAX_EXPONENT:
                raise _ParseError("too_large", f"Exponents may be at most {MAX_EXPONENT}.")
            factor *= max(1.0, size)
            if factor > MAX_EXPONENT_PRODUCT:
                raise _ParseError("too_large", "The nested powers are too large to check.")
            _bound_powers(base, factor)
            return
    for arg in node.args:
        _bound_powers(arg, factor)


def _parse_side(text: str, context: _Context) -> sympy.Expr:
    if not text.strip():
        raise _ParseError("empty", "One side of the expression is empty.")
    _check_names(text, context)
    try:
        unevaluated = parse_expr(
            text,
            local_dict=context.local_dict(),
            transformations=_TRANSFORMATIONS,
            global_dict={"__builtins__": {}, **_GLOBALS},
            evaluate=False,
        )
        if not isinstance(unevaluated, sympy.Basic):
            raise _ParseError("syntax", "The answer is not a single expression.")
        _bound_powers(unevaluated)
        result = parse_expr(
            text,
            local_dict=context.local_dict(),
            transformations=_TRANSFORMATIONS,
            global_dict={"__builtins__": {}, **_GLOBALS},
        )
    except _ParseError:
        raise
    except RecursionError as error:
        raise _ParseError("syntax", "The expression is nested too deeply.") from error
    except Exception as error:  # SyntaxError, TokenError, TypeError, SympifyError, ...
        raise _ParseError("syntax", "The expression could not be read.") from error
    if not isinstance(result, sympy.Expr):
        raise _ParseError("syntax", "The answer is not a single expression.")
    declared = set(context.symbols.values())
    undeclared = sorted(str(symbol) for symbol in result.free_symbols if symbol not in declared)
    if undeclared:
        raise _ParseError(
            "unknown_name", f"'{undeclared[0]}' is not a variable this question accepts."
        )
    return result


def _parse(text: str, context: _Context) -> tuple[sympy.Expr, sympy.Expr | None]:
    """``(expression, None)``, or ``(lhs, rhs)`` in equation mode."""
    if not isinstance(text, str) or not text.strip():
        raise _ParseError("empty", "No answer was given.")
    if len(text) > MAX_ANSWER_LENGTH:
        raise _ParseError("too_long", f"Answers may be at most {MAX_ANSWER_LENGTH} characters.")
    if "__" in text:
        raise _ParseError("forbidden", "'__' is not allowed in an answer.")
    if not _ALLOWED_CHARS.fullmatch(text):
        raise _ParseError(
            "forbidden", "Only letters, digits, spaces and + - * / ^ ( ) . , = are allowed."
        )
    sides = text.split("=")
    if context.equation:
        if len(sides) != 2:
            raise _ParseError("syntax", "Write the answer as one equation: left = right.")
        return _parse_side(sides[0], context), _parse_side(sides[1], context)
    if len(sides) != 1:
        raise _ParseError("syntax", "Write an expression, not an equation.")
    return _parse_side(text, context), None


# --- equivalence ----------------------------------------------------------------------------

_T = TypeVar("_T")


def _with_budget(fn: Callable[[], _T], seconds: float) -> tuple[bool, _T | None]:
    """Run ``fn`` in a daemon thread; ``(False, None)`` if it does not finish in time."""
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except Exception as error:  # surfaced to the caller as "not proven"
            box["error"] = error

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive() or "error" in box:
        return False, None
    return True, box.get("value")


def _symbolically_equal(answer: sympy.Expr, expected: sympy.Expr, equation: bool) -> bool:
    if equation:
        ratio = sympy.simplify(answer / expected)
        return not ratio.free_symbols and bool(ratio.is_nonzero) and bool(ratio.is_finite)
    return sympy.simplify(answer - expected) == 0


def _value(expr: sympy.Expr, point: dict[sympy.Symbol, sympy.Float]) -> float | None:
    """The real value of ``expr`` at ``point``, or ``None`` if it is not finite and real."""
    try:
        value = complex(expr.evalf(20, subs=point))
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None
    if not (math.isfinite(value.real) and math.isfinite(value.imag)):
        return None
    if abs(value.imag) > 1e-12 * max(1.0, abs(value.real)):
        return None
    return value.real


def _numerically_equal(
    answer: sympy.Expr, expected: sympy.Expr, spec: SymbolicSpec, symbols: list[sympy.Symbol]
) -> bool:
    rng = random.Random(zlib.crc32(spec.expected.encode("utf-8")))
    needed = spec.numeric_samples if symbols else 1
    usable = 0
    ratio: float | None = None
    for _ in range(4 * spec.numeric_samples if symbols else 1):
        point = {symbol: sympy.Float(rng.uniform(*SAMPLE_RANGE)) for symbol in symbols}
        a, b = _value(answer, point), _value(expected, point)
        if a is None or b is None:
            continue
        if spec.equation:
            if abs(b) < 1e-12:
                if abs(a) > 1e-12:
                    return False
                continue
            current = a / b
            if ratio is None:
                if abs(current) < 1e-12:
                    return False
                ratio = current
            elif abs(current - ratio) > spec.tolerance * max(1.0, abs(ratio)):
                return False
        elif abs(a - b) > spec.tolerance * max(1.0, abs(b)):
            return False
        usable += 1
        if usable >= needed:
            break
    return usable >= (math.ceil(spec.numeric_samples / 2) if symbols else 1)


# --- the grader -----------------------------------------------------------------------------


def _context_issues(spec: SymbolicSpec) -> tuple[_Context | None, list[SpecIssue]]:
    issues: list[SpecIssue] = []
    names = spec.allowed_functions if spec.allowed_functions is not None else list(SAFE_NAMES)
    unknown = [name for name in names if name not in SAFE_NAMES]
    if unknown:
        issues.append(
            SpecIssue("unknown_function", f"Not a supported function or constant: {unknown}.")
        )
    functions = {name: SAFE_NAMES[name] for name in names if name in SAFE_NAMES}
    for name in spec.variables:
        if not _IDENTIFIER.fullmatch(name) or "__" in name or keyword.iskeyword(name):
            issues.append(SpecIssue("invalid_variable", f"'{name}' is not a valid variable name."))
        elif name in functions or name in SAFE_NAMES or name in _GLOBALS:
            issues.append(
                SpecIssue("variable_collides", f"Variable '{name}' collides with a function name.")
            )
    if len(set(spec.variables)) != len(spec.variables):
        issues.append(SpecIssue("duplicate_variable", "A variable is declared twice."))
    if spec.numeric_samples < 3:
        issues.append(SpecIssue("too_few_samples", "numeric_samples must be at least 3."))
    if spec.equation and spec.expected.count("=") != 1:
        issues.append(
            SpecIssue("equation_form", "In equation mode, expected must contain exactly one '='.")
        )
    if issues:
        return None, issues
    symbols = {name: sympy.Symbol(name) for name in spec.variables}
    return _Context(symbols=symbols, functions=functions, equation=spec.equation), []


def _prepare(
    spec: SymbolicSpec,
) -> tuple[_Context | None, tuple[sympy.Expr, sympy.Expr | None] | None, list[SpecIssue]]:
    context, issues = _context_issues(spec)
    if context is None:
        return None, None, issues
    try:
        expected = _parse(spec.expected, context)
    except _ParseError as error:
        code = "undeclared_symbol" if error.kind == "unknown_name" else "expected_unparseable"
        return context, None, [SpecIssue(code, f"expected: {error.message}")]
    return context, expected, []


class SymbolicEquivalenceGrader:
    capability = CAPABILITY
    version = "1"
    spec_model = SymbolicSpec

    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]:
        try:
            parsed = parse_spec(SymbolicSpec, spec)
        except SpecError as error:
            return [SpecIssue("invalid_spec", str(error))]
        assert isinstance(parsed, SymbolicSpec)
        context, expected, issues = _prepare(parsed)
        if issues:
            return issues
        assert context is not None and expected is not None
        if self.grade(spec, parsed.expected).score != 1.0:
            return [
                SpecIssue(
                    "reference_not_full_marks",
                    "The expected answer does not grade as equivalent to itself.",
                )
            ]
        reference = expected[0] - expected[1] if expected[1] is not None else expected[0]
        symbols = [context.symbols[name] for name in sorted(context.symbols)]
        done, sampled = _with_budget(
            lambda: _numerically_equal(reference, reference, parsed, symbols), NUMERIC_BUDGET_S
        )
        if not (done and sampled):
            return [
                SpecIssue(
                    "no_real_samples",
                    "The expected answer is not finite and real at enough points in [-3, 3], "
                    "so answers written differently cannot be checked numerically.",
                )
            ]
        return []

    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult:
        parsed = parse_spec(SymbolicSpec, spec)
        assert isinstance(parsed, SymbolicSpec)
        context, expected, issues = _prepare(parsed)
        if issues or context is None or expected is None:
            raise SpecError("; ".join(f"{issue.code}: {issue.message}" for issue in issues))
        feedback = parsed.explanation
        try:
            given = _parse(answer, context)
        except _ParseError as error:
            return GradeResult(score=0.0, feedback=feedback, format_error=error.message)

        if parsed.equation:
            assert given[1] is not None and expected[1] is not None
            answer_expr = given[0] - given[1]
            expected_expr = expected[0] - expected[1]
        else:
            answer_expr, expected_expr = given[0], expected[0]

        done, proven = _with_budget(
            lambda: _symbolically_equal(answer_expr, expected_expr, parsed.equation),
            SIMPLIFY_BUDGET_S,
        )
        if done and proven:
            return GradeResult(score=1.0, feedback=feedback)
        symbols = [context.symbols[name] for name in sorted(context.symbols)]
        done, equal = _with_budget(
            lambda: _numerically_equal(answer_expr, expected_expr, parsed, symbols),
            NUMERIC_BUDGET_S,
        )
        if not done:
            return GradeResult(
                score=0.0,
                feedback=feedback,
                format_error="The answer is too complex to check in time.",
            )
        return GradeResult(score=1.0 if equal else 0.0, feedback=feedback)


def build(executor_factory: Callable[[], Executor]) -> list[Grader]:
    """The symbolic graders; they never run code, so the executor is unused."""
    return [SymbolicEquivalenceGrader()]
