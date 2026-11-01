"""The headless check of html tutorial blocks (Phase 5, Task 23). Needs Playwright's Chromium."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.tutorials.html_check import HtmlCheckUnavailable, check_html_block
from app.tutorials.renderers import LineNote, stepper_html
from app.tutorials.schema import RecipeCheck
from app.tutorials.tools.python_trace import TraceStep, python_trace

pytest.importorskip("playwright.sync_api")

PROGRAM = (
    "def double(x):\n    return 2 * x\n\n"
    "total = 0\nfor n in [1, 2]:\n    total += double(n)\nprint(total)\n"
)
STEPPER = [RecipeCheck.HTML_LOADS, RecipeCheck.TRACE_MATCHES]


def _stepper(code: str = PROGRAM) -> dict[str, Any]:
    steps = python_trace(code).steps
    notes = [LineNote(line=6, note="Adds the doubled number to the total.")]
    return {
        "title": "Doubling",
        "code": code,
        "trace": [step.model_dump() for step in steps],
        "notes": [note.model_dump() for note in notes],
        "html": stepper_html("Doubling", code, steps, notes),
    }


def _check(payload: dict[str, Any], checks: list[RecipeCheck] = STEPPER) -> list[str]:
    try:
        return check_html_block(payload, checks)
    except HtmlCheckUnavailable as exc:
        pytest.skip(str(exc))


def test_a_correct_stepper_passes() -> None:
    payload = _stepper()
    assert len(payload["trace"]) > 10
    assert _check(payload) == []


def test_a_stepper_showing_a_different_run_fails() -> None:
    # The page embeds a tampered trace; the payload keeps the recorded one.
    payload = _stepper()
    tampered = json.loads(json.dumps(payload["trace"]))
    tampered[5]["locals"]["total"] = "99"
    payload["html"] = stepper_html(
        "Doubling",
        PROGRAM,
        [TraceStep.model_validate(step) for step in tampered],
        [],
    )
    (problem,) = _check(payload)
    assert problem.startswith("step 6: shows variables")


def test_a_stepper_with_a_missing_step_fails() -> None:
    payload = _stepper()
    shorter = [TraceStep.model_validate(step) for step in payload["trace"][:-1]]
    payload["html"] = stepper_html("Doubling", PROGRAM, shorter, [])
    (problem,) = _check(payload)
    assert "Next is disabled" in problem


def test_a_broken_stepper_script_fails() -> None:
    payload = _stepper()
    payload["html"] = payload["html"].replace('getElementById("next")', 'getElementById("nxt")')
    problems = _check(payload)
    assert any(problem.startswith("page error") for problem in problems)


def test_a_console_error_fails_a_plain_html_block() -> None:
    html = "<!doctype html><p>hi</p><script>console.error('boom')</script>"
    assert _check({"html": html}, [RecipeCheck.HTML_LOADS]) == ["console error: boom"]
    assert _check({"html": "<!doctype html><p>fine</p>"}, [RecipeCheck.HTML_LOADS]) == []


def test_a_block_that_reaches_the_network_fails() -> None:
    html = '<!doctype html><img src="https://example.com/x.png">'
    problems = _check({"html": html}, [RecipeCheck.HTML_LOADS])
    assert "the block tries to load https://example.com/x.png" in problems
