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

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["nav_sections"] = NAV_SECTIONS
templates.env.globals["app_version"] = __version__


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
