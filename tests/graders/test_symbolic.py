"""symbolic.expression_equivalence (C4)."""

from __future__ import annotations

import multiprocessing
import os
import subprocess
import threading
import time
from typing import Any

import pytest

import graders
from graders import SpecError, symbolic
from graders.symbolic import SymbolicEquivalenceGrader

GRADER = SymbolicEquivalenceGrader()
DERIVATIVE = {"expected": "2*x*sin(x) + x**2*cos(x)", "variables": ["x"]}


def _never_proves(*args: object) -> bool:
    """Stands in for simplify. Module-level: the budgeted work runs in a worker process, which
    receives the function by reference (``test_symbolic._never_proves``)."""
    return False


def _spin(*args: object) -> None:
    while True:
        pass


def _score(spec: dict[str, Any], answer: str) -> float:
    result = GRADER.grade(spec, answer)
    if result.format_error:
        assert result.score == 0.0
    return result.score


@pytest.mark.parametrize(
    "answer",
    [
        "x*(2*sin(x)+x*cos(x))",
        "2*x*sin(x)+x**2*cos(x)",
        "2x sin x + x^2 cos x",
        "x^2 cos(x) + 2 x sin(x)",
    ],
)
def test_equivalent_forms_are_correct(answer: str) -> None:
    result = GRADER.grade(DERIVATIVE, answer)
    assert result.format_error is None
    assert result.score == 1.0


@pytest.mark.parametrize("answer", ["x**2*sin(x)", "2*x*cos(x) + x**2*sin(x)", "0"])
def test_non_equivalent_is_wrong_not_a_format_error(answer: str) -> None:
    result = GRADER.grade(DERIVATIVE, answer)
    assert result.score == 0.0
    assert result.format_error is None


def test_polynomial_expansion() -> None:
    spec = {"expected": "(x+1)**2", "variables": ["x"]}
    assert _score(spec, "x**2+2*x+1") == 1.0
    assert _score(spec, "x**2+x+1") == 0.0


def test_numeric_only_expected() -> None:
    spec = {"expected": "sqrt(2)/2", "variables": []}
    assert _score(spec, "1/sqrt(2)") == 1.0
    assert _score(spec, "sin(pi/4)") == 1.0
    assert _score(spec, "0.70710678118654752") == 1.0
    assert _score(spec, "0.7") == 0.0


def test_multiple_variables_and_split_symbols() -> None:
    spec = {"expected": "x*y + y", "variables": ["x", "y"]}
    assert _score(spec, "xy + y") == 1.0
    assert _score(spec, "y(x+1)") == 1.0


def test_numeric_fallback_when_simplify_does_not_prove(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(symbolic, "_symbolically_equal", _never_proves)
    assert _score(DERIVATIVE, "x*(2*sin(x)+x*cos(x))") == 1.0
    assert _score(DERIVATIVE, "x**2*sin(x)") == 0.0


def test_points_outside_the_domain_are_skipped() -> None:
    spec = {"expected": "x", "variables": ["x"]}
    # sqrt(x)^2 is only real for x >= 0: about half the draws are skipped, then it matches.
    assert _score(spec, "sqrt(x)^2") == 1.0
    assert _score(spec, "abs(x)") == 0.0


def test_ln_maps_to_log() -> None:
    spec = {"expected": "log(x**2)", "variables": ["x"], "allowed_functions": ["log", "ln"]}
    assert _score(spec, "2 ln(abs(x))") == 0.0  # abs is not whitelisted here -> format error
    assert GRADER.grade(spec, "2 ln(abs(x))").format_error
    assert _score(spec, "ln(x^2)") == 1.0


def test_restricted_functions_refuse_others() -> None:
    spec = {"expected": "x**2", "variables": ["x"], "allowed_functions": []}
    result = GRADER.grade(spec, "sqrt(x**4)")
    assert result.score == 0.0 and result.format_error


def test_equation_mode() -> None:
    spec = {"expected": "y = 2x", "variables": ["x", "y"], "equation": True}
    assert _score(spec, "2y = 4x") == 1.0
    assert _score(spec, "y - 2x = 0") == 1.0
    assert _score(spec, "-y = -2*x") == 1.0
    assert _score(spec, "y = 3x") == 0.0
    assert _score(spec, "x = x") == 0.0  # identically zero is not a nonzero multiple
    assert GRADER.grade(spec, "y - 2x").format_error  # not an equation
    assert GRADER.grade(spec, "y = 2x = 2x").format_error


def test_equation_fallback_numeric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(symbolic, "_symbolically_equal", _never_proves)
    spec = {"expected": "y = 2x", "variables": ["x", "y"], "equation": True}
    assert _score(spec, "2y = 4x") == 1.0
    assert _score(spec, "y = 3x") == 0.0


def test_equals_sign_outside_equation_mode_is_a_format_error() -> None:
    assert GRADER.grade(DERIVATIVE, "y = 2x").format_error


def test_undeclared_variable_is_a_format_error() -> None:
    result = GRADER.grade(DERIVATIVE, "2*x*sin(y) + x**2*cos(x)")
    assert result.score == 0.0
    assert result.format_error and "'y'" in result.format_error


def test_explanation_is_feedback_on_every_grade() -> None:
    spec = {**DERIVATIVE, "explanation": "Product rule."}
    assert GRADER.grade(spec, "x*(2*sin(x)+x*cos(x))").feedback == "Product rule."
    assert GRADER.grade(spec, "x").feedback == "Product rule."
    assert GRADER.grade(spec, "__import__('os')").feedback == "Product rule."


MALICIOUS = [
    "__import__('os').system('echo hi')",
    "x.__class__",
    "lambda: 1",
    "open('f')",
    "exec('1')",
    "().__class__",
    "eval('1')",
    "x.diff(x)",
    "(1).real",
    "globals()",
    "Symbol('x')",
    "Integer(2)",
    "x if x else x",
    "[x for x in (1,)]",
    "0x10",
    "2j",
    "x; x",
    chr(0xFF3F) * 2 + "import" + chr(0xFF3F) * 2,  # fullwidth "__" (NFKC-normalises)
]


@pytest.mark.parametrize("answer", MALICIOUS)
def test_malicious_input_is_a_format_error_without_side_effects(
    answer: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("the grader tried to run something")

    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.chdir(tmp_path)
    result = GRADER.grade(DERIVATIVE, answer)
    assert result.score == 0.0
    assert result.format_error
    assert not (tmp_path / "f").exists()


@pytest.mark.parametrize(
    "answer",
    [
        "__import__('os').system('echo hi')",
        "x.__class__",
        "lambda: 1",
        "open('f')",
        "exec('1')",
        "().__class__",
    ],
)
def test_malicious_input_never_reaches_parse_expr(
    answer: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = symbolic.parse_expr

    def recording(text: str, *args: Any, **kwargs: Any) -> Any:
        calls.append(text)
        return real(text, *args, **kwargs)

    monkeypatch.setattr(symbolic, "parse_expr", recording)
    assert GRADER.grade(DERIVATIVE, answer).format_error
    assert answer not in calls


def test_parse_globals_have_no_builtins() -> None:
    # Even if a name got past the screen, eval would not find builtins.
    with pytest.raises(NameError):
        eval("open", {"__builtins__": {}, **symbolic._GLOBALS}, {})


@pytest.mark.parametrize("answer", ["9^9^9", "x^1000", "(x^50)^50", "2^(10^10)", "10^(9^9)"])
def test_huge_powers_are_refused_not_computed(answer: str) -> None:
    result = GRADER.grade(DERIVATIVE, answer)
    assert result.score == 0.0 and result.format_error


def test_very_long_input_is_a_format_error() -> None:
    result = GRADER.grade(DERIVATIVE, "x+" * 200 + "x")
    assert result.score == 0.0
    assert result.format_error and "300" in result.format_error


@pytest.mark.parametrize("answer", ["", "   ", "\n", "()", "x +", "sin(", ")"])
def test_empty_or_broken_answer_is_a_format_error(answer: str) -> None:
    result = GRADER.grade(DERIVATIVE, answer)
    assert result.score == 0.0 and result.format_error


def test_check_spec_accepts_good_specs() -> None:
    assert GRADER.check_spec(DERIVATIVE) == []
    assert GRADER.check_spec({"expected": "sqrt(2)/2", "variables": []}) == []
    assert (
        GRADER.check_spec({"expected": "y = 2x", "variables": ["x", "y"], "equation": True}) == []
    )


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        ({"expected": "x +", "variables": ["x"]}, "expected_unparseable"),
        ({"expected": "x*y", "variables": ["x"]}, "undeclared_symbol"),
        ({"expected": "x", "variables": ["1x"]}, "invalid_variable"),
        ({"expected": "x", "variables": ["x", "lambda"]}, "invalid_variable"),
        ({"expected": "x", "variables": ["x", "a__b"]}, "invalid_variable"),
        ({"expected": "x", "variables": ["x", "sin"]}, "variable_collides"),
        ({"expected": "x", "variables": ["x", "Integer"]}, "variable_collides"),
        ({"expected": "x", "variables": ["x"], "numeric_samples": 2}, "too_few_samples"),
        ({"expected": "y - 2*x", "variables": ["x", "y"], "equation": True}, "equation_form"),
        ({"expected": "y = 2x = z", "variables": ["x", "y"], "equation": True}, "equation_form"),
        ({"expected": "x", "variables": ["x"], "allowed_functions": ["eval"]}, "unknown_function"),
        ({"expected": "sqrt(-1 - x**2)", "variables": ["x"]}, "no_real_samples"),
        ({"expected": "x", "variables": ["x"], "bogus": 1}, "invalid_spec"),
        ({"variables": ["x"]}, "invalid_spec"),
    ],
)
def test_check_spec_issues(spec: dict[str, Any], code: str) -> None:
    issues = GRADER.check_spec(spec)
    assert code in [issue.code for issue in issues], issues


@pytest.mark.parametrize(
    "spec",
    [
        {"variables": ["x"]},
        {"expected": "x", "variables": ["x"], "extra": True},
        {"expected": "x +", "variables": ["x"]},
        {"expected": "x*y", "variables": ["x"]},
        {"expected": "x", "variables": ["x"], "numeric_samples": 1},
        {"expected": "x", "variables": ["x"], "tolerance": 0},
    ],
)
def test_broken_spec_raises_spec_error(spec: dict[str, Any]) -> None:
    with pytest.raises(SpecError):
        GRADER.grade(spec, "x")


def test_registry_builds_it() -> None:
    graders.set_executor(None)
    grader = graders.get_grader("symbolic.expression_equivalence")
    assert grader.capability == "symbolic.expression_equivalence"
    assert grader.version == "1"
    assert isinstance(grader, graders.Grader)
    assert grader.grade(DERIVATIVE, "x*(2*sin(x)+x*cos(x))").score == 1.0


# --- C9: the time budget kills the work --------------------------------------------------------

PATHOLOGICAL = "sin(x)^60*cos(x)^60 - (sin(2x)/2)^60 + x"  # simplify takes ~3 s, numeric is fast


def _warm_pool() -> None:
    assert symbolic._with_budget(abs, (-1,), 30.0) == (True, 1)
    for worker in list(symbolic._idle):
        assert worker.wait_ready(60.0)


def _live_workers() -> set[int]:
    return {p.pid for p in multiprocessing.active_children() if p.name == symbolic._WORKER_NAME}


def _idle_workers() -> set[int]:
    return {worker.process.pid for worker in symbolic._idle}


def test_a_budget_overrun_terminates_the_worker() -> None:
    _warm_pool()
    threads = threading.active_count()
    started = time.perf_counter()
    assert symbolic._with_budget(_spin, (), 0.3) == (False, None)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.3 + 1.0, elapsed
    # The spinning worker is gone: every live worker is an idle one, and no thread was left.
    assert _live_workers() <= _idle_workers()
    assert threading.active_count() == threads
    # And the pool still works.
    assert symbolic._with_budget(abs, (-2,), 30.0) == (True, 2)


def test_a_pathological_answer_returns_within_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    _warm_pool()
    monkeypatch.setattr(symbolic, "SIMPLIFY_BUDGET_S", 0.5)
    spec = {"expected": "x", "variables": ["x"]}
    started = time.perf_counter()
    result = GRADER.grade(spec, PATHOLOGICAL)
    elapsed = time.perf_counter() - started
    assert result.score == 1.0  # simplify was cut off; the numeric check decided
    assert elapsed < 0.5 + 1.5, elapsed
    assert _live_workers() <= _idle_workers()


def test_both_budgets_blown_is_a_format_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _warm_pool()
    monkeypatch.setattr(symbolic, "_numerically_equal", _spin)
    monkeypatch.setattr(symbolic, "SIMPLIFY_BUDGET_S", 0.3)
    monkeypatch.setattr(symbolic, "NUMERIC_BUDGET_S", 0.3)
    started = time.perf_counter()
    result = GRADER.grade({"expected": "x", "variables": ["x"]}, PATHOLOGICAL)
    assert time.perf_counter() - started < 0.6 + 1.5
    assert result.score == 0.0 and result.format_error
    assert _live_workers() <= _idle_workers()


def test_an_exception_in_the_worker_is_not_proven() -> None:
    assert symbolic._with_budget(int, ("not a number",), 30.0) == (False, None)
