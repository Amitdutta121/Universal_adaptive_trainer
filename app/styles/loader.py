"""Load the style library from YAML (``styles/<subject>/<id>.yaml``).

One file per style, so a contributed style is one new file in a PR. The subject comes from the
directory and the id from the file name; a file may repeat either, but only with the same
value. ``styles/<subject>/order.txt`` lists ids in display order; styles it does not list come
after, sorted by id, so a contributor never has to edit it.

A bad file fails loudly with its path and the offending field: the library is shipped content,
and a style that silently disappeared would orphan the questions that store its id.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.styles.schema import QuestionStyle

#: Repo-root ``styles/``. The app runs from the source tree (the Dockerfile copies it beside
#: ``app/``), so this resolves both locally and in the image.
STYLES_DIR = Path(__file__).resolve().parents[2] / "styles"

ORDER_FILE = "order.txt"


class StyleFileError(ValueError):
    """A style file that cannot be loaded. The message names the file and the field."""


def load_style_file(path: Path, subject: str) -> QuestionStyle:
    """Parse and validate one style file of ``subject``."""
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise StyleFileError(f"{path}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise StyleFileError(f"{path}: expected a mapping of style fields at the top level")
    for field, expected in (("subject", subject), ("id", path.stem)):
        if data.setdefault(field, expected) != expected:
            raise StyleFileError(
                f"{path}: field '{field}' is {data[field]!r} but must be {expected!r} "
                f"(the {'directory' if field == 'subject' else 'file'} name)"
            )
    try:
        return QuestionStyle.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"field '{'.'.join(str(part) for part in error['loc'])}': {error['msg']}"
            for error in exc.errors()
        )
        raise StyleFileError(f"{path}: {problems}") from exc


def load_subject(directory: Path) -> list[QuestionStyle]:
    """Every style of one subject directory, in display order."""
    subject = directory.name
    styles = {path.stem: load_style_file(path, subject) for path in directory.glob("*.yaml")}
    order_path = directory / ORDER_FILE
    order = (
        [line.strip() for line in order_path.read_text(encoding="utf-8").splitlines()]
        if order_path.exists()
        else []
    )
    order = [style_id for style_id in order if style_id]
    missing = [style_id for style_id in order if style_id not in styles]
    if missing:
        raise StyleFileError(f"{order_path}: lists ids with no style file: {', '.join(missing)}")
    rest = sorted(style_id for style_id in styles if style_id not in order)
    return [styles[style_id] for style_id in [*order, *rest]]


def load_libraries(root: Path = STYLES_DIR) -> dict[str, list[QuestionStyle]]:
    """Every subject's library under ``root``, keyed by subject storage key."""
    if not root.is_dir():
        return {}
    return {
        directory.name: load_subject(directory)
        for directory in sorted(root.iterdir())
        if directory.is_dir()
    }
