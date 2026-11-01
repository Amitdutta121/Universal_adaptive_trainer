"""Headless check of html tutorial blocks at generation time (Task 23).

Every html block is loaded in headless Chromium (Playwright) before it is saved as a draft:

- ``html_loads``: a console error, an uncaught page error or any network request fails it. The
  browser blocks every request -- the frontend's sandbox CSP would too -- and reports it, so a
  block that tries to reach the network never ships.
- ``trace_matches``: the stepper is clicked through from first step to last and every displayed
  step -- line, variables, output -- must equal the recorded ``python_trace`` step it embeds.

Needs the optional ``htmlcheck`` extra and its browser (``playwright install chromium``). When
they are missing the check raises :class:`HtmlCheckUnavailable`; the generator then fails the
block rather than ship html nobody has loaded.
"""

from __future__ import annotations

from typing import Any

from app.tutorials.schema import RecipeCheck

#: Milliseconds a block may take to load, and to answer one click.
LOAD_TIMEOUT_MS = 10_000

#: Reads what the stepper shows now (see ``stepper_html``'s element ids).
_READ_STEP = """() => {
  const position = document.getElementById("position");
  const locals = {};
  document.querySelectorAll("#locals tr[data-name]").forEach((tr) => {
    locals[tr.getAttribute("data-name")] = tr.children[1].textContent;
  });
  const current = document.querySelector("#code li.current");
  return {
    step: Number(position.getAttribute("data-step")),
    line: Number(position.getAttribute("data-line")),
    current: current ? Number(current.getAttribute("data-line")) : null,
    locals: locals,
    stdout: document.getElementById("stdout").textContent,
    nextDisabled: document.getElementById("next").disabled,
  };
}"""


class HtmlCheckUnavailable(RuntimeError):
    """Playwright or its browser is not installed, so html blocks cannot be checked."""


def check_html_block(payload: dict[str, Any], checks: list[RecipeCheck]) -> list[str]:
    """Problems found loading (and, for a stepper, stepping through) an html block's payload."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise HtmlCheckUnavailable(
            "html blocks cannot be checked: install the 'htmlcheck' extra "
            "and run 'playwright install chromium'"
        ) from exc

    problems: list[str] = []
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except PlaywrightError as exc:
                raise HtmlCheckUnavailable(
                    f"html blocks cannot be checked: no browser ({exc.message.splitlines()[0]}); "
                    "run 'playwright install chromium'"
                ) from exc
            try:
                page = browser.new_page()
                page.set_default_timeout(LOAD_TIMEOUT_MS)
                page.on(
                    "console",
                    lambda message: (
                        problems.append(f"console error: {message.text}")
                        if message.type == "error"
                        else None
                    ),
                )
                page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
                page.route("**/*", lambda route: _refuse(route, problems))
                page.set_content(payload.get("html", ""), wait_until="load")
                if RecipeCheck.TRACE_MATCHES in checks and not problems:
                    problems.extend(_step_through(page, payload.get("trace", [])))
            finally:
                browser.close()
    except PlaywrightError as exc:
        problems.append(f"the block did not load: {exc.message.splitlines()[0]}")
    return problems


def _refuse(route: Any, problems: list[str]) -> None:
    problems.append(f"the block tries to load {route.request.url}")
    route.abort()


def _step_through(page: Any, trace: list[dict[str, Any]]) -> list[str]:
    """Click through the stepper; every displayed step must equal the recorded one."""
    if not trace:
        return ["the stepper has no recorded steps"]
    for index, expected in enumerate(trace):
        shown = page.evaluate(_READ_STEP)
        where = f"step {index + 1}"
        if shown["step"] != index:
            return [f"{where}: the stepper shows step {shown['step'] + 1}"]
        if shown["line"] != expected["line"] or shown["current"] != expected["line"]:
            return [
                f"{where}: shows line {shown['line']} (highlighted {shown['current']}) "
                f"but the run was on line {expected['line']}"
            ]
        if shown["locals"] != expected["locals"]:
            return [
                f"{where}: shows variables {shown['locals']} but the run had {expected['locals']}"
            ]
        if shown["stdout"] != expected["stdout"]:
            return [
                f"{where}: shows output {shown['stdout']!r} but the run had {expected['stdout']!r}"
            ]
        last = index == len(trace) - 1
        if shown["nextDisabled"] != last:
            return [f"{where}: Next is {'enabled' if last else 'disabled'}"]
        if not last:
            page.click("#next")
    return []
