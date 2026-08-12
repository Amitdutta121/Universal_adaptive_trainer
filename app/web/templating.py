"""Jinja2 setup and the shared render helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import get_settings
from app.web.navigation import NAV_SECTIONS

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

#: Opens and closes a fenced code block in a generated prompt.
FENCE = "```"


def fenced_segments(text: str | None) -> list[tuple[str, str]]:
    """Split a prompt into ``("text" | "code", body)`` segments for display.

    Two question types -- multiple choice and true/false -- have no ``code``
    field in their generation schema (``app.generation.schemas``), so a model
    writing a code-reading question has nowhere to put the snippet except the
    prompt, where it arrives fenced. Rendering the fence markers verbatim makes
    those questions read as malformed during review, which risks a professor
    penalising a formatting artefact as if it were a defect.

    This is display only: nothing is rewritten in the database, and the judge
    still sees the prompt exactly as generated. Splitting is a literal ``str``
    split rather than a pattern match, and an odd number of fences is treated as
    prose -- a malformed prompt is shown as written rather than guessed at.
    """
    if not text:
        return []
    if text.count(FENCE) % 2 != 0:
        return [("text", text)]

    segments: list[tuple[str, str]] = []
    for index, part in enumerate(text.split(FENCE)):
        inside_fence = index % 2 == 1
        if not inside_fence:
            if part.strip():
                segments.append(("text", part.strip()))
            continue
        body = _without_language_tag(part).strip("\n")
        if body.strip():
            segments.append(("code", body))
    return segments


def _without_language_tag(block: str) -> str:
    """Drop the opening ``python`` label from a fenced block, if it has one."""
    first_line, newline, rest = block.partition("\n")
    if newline and first_line.strip() and not first_line.strip().startswith(" "):
        # A language tag is a bare word; anything else is the first line of code.
        return rest if first_line.strip().isalnum() else block
    return block


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["nav_sections"] = NAV_SECTIONS
templates.env.globals["app_version"] = __version__
templates.env.filters["fenced_segments"] = fenced_segments


def render(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> HTMLResponse:
    """Render ``template_name`` with the common context applied."""
    settings = get_settings()
    merged: dict[str, Any] = {
        "app_name": settings.app_name,
        "environment": settings.environment.value,
        "active_section": None,
    }
    merged.update(context or {})
    return templates.TemplateResponse(request, template_name, merged, status_code=status_code)


def render_error_page(
    request: Request, *, status_code: int, message: str, detail: str | None = None
) -> HTMLResponse:
    """Render the shared error page. Used by the exception handlers."""
    settings = get_settings()
    return render(
        request,
        "error.html",
        {
            "page_title": f"Error {status_code}",
            "status_code": status_code,
            "message": message,
            # Details can carry internals, so only show them in development.
            "detail": detail if settings.is_development else None,
        },
        status_code=status_code,
    )
