"""Computed question figures (ADR-080): one SVG file per stored key.

Served as an image only: students load it through ``<img>``, which never runs a script in an
SVG, and the headers stop a browser that opens the URL directly from running one either.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from app.errors import NotFoundError
from app.figures.storage import FigureStorageError, read_svg

router = APIRouter(prefix="/figures", tags=["figures"])

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    # Content-addressed: the bytes behind a key never change.
    "Cache-Control": "public, max-age=31536000, immutable",
}


@router.get("/{course_id}/{name}.svg", response_class=Response)
def get_figure(course_id: int, name: str) -> Response:
    try:
        svg = read_svg(f"{course_id}/{name}.svg")
    except (FigureStorageError, FileNotFoundError) as error:
        raise NotFoundError("Figure not found.") from error
    return Response(content=svg, media_type="image/svg+xml", headers=_HEADERS)
