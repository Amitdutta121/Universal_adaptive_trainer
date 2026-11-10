"""Computed figures as files: the database keeps only a key (ADR-080 decision 4).

Keys are ``<course_id>/<sha256>.svg`` under ``settings.figure_dir``: content-addressed, so the
same SVG is stored once, and unguessable, so the public figure route cannot be enumerated.
Moving to object storage later replaces this module only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import get_settings
from app.figures.schema import FIGURE_KEY

#: Larger than any plot the generator should draw (real ones are 8-13 KB).
MAX_SVG_BYTES = 512 * 1024


class FigureStorageError(ValueError):
    """An SVG that may not be stored, or a key that is not a stored figure."""


def _path(key: str) -> Path:
    if not FIGURE_KEY.match(key):
        raise FigureStorageError(f"not a figure key: {key!r}")
    root = Path(get_settings().figure_dir).resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root):  # belt and braces: the regex already forbids it
        raise FigureStorageError(f"not a figure key: {key!r}")
    return path


def save_svg(course_id: int, svg: str) -> str:
    """Store ``svg`` for ``course_id`` and return its key."""
    if isinstance(course_id, bool) or not isinstance(course_id, int) or course_id < 0:
        raise FigureStorageError("course_id must be a non-negative integer")
    data = svg.encode("utf-8")
    if len(data) > MAX_SVG_BYTES:
        raise FigureStorageError(f"the SVG is {len(data)} bytes; the limit is {MAX_SVG_BYTES}")
    head = svg.lstrip()[:5].lower()
    if not (head.startswith("<svg") or head.startswith("<?xml")):
        raise FigureStorageError("the figure is not an SVG")
    key = f"{course_id}/{hashlib.sha256(data).hexdigest()}.svg"
    path = _path(key)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return key


def read_svg(key: str) -> bytes:
    """The stored SVG for ``key``. ``FileNotFoundError`` when there is none."""
    return _path(key).read_bytes()
