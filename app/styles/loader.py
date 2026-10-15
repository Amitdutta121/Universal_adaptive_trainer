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
    return parse_style_text(
        path.read_text(encoding="utf-8"), subject, source=str(path), file_id=path.stem
    )


def parse_style_text(
    text: str, subject: str, *, source: str, file_id: str | None = None
) -> QuestionStyle:
    """Parse and validate one style's YAML. ``file_id`` is the id its file name implies, if any.

    ``source`` names the text in every error (a path, or "the pasted style").
    """
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StyleFileError(f"{source}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise StyleFileError(f"{source}: expected a mapping of style fields at the top level")
    expected = {"subject": (subject, "the directory")}
    if file_id is not None:
        expected["id"] = (file_id, "the file name")
    for field, (value, origin) in expected.items():
        if data.setdefault(field, value) != value:
            raise StyleFileError(
                f"{source}: field '{field}' is {data[field]!r} but must be {value!r} ({origin})"
            )
    try:
        return QuestionStyle.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"field '{'.'.join(str(part) for part in error['loc'])}': {error['msg']}"
            for error in exc.errors()
        )
        raise StyleFileError(f"{source}: {problems}") from exc


class _Dumper(yaml.SafeDumper):
    """Multi-line strings (code, expected output) as ``|`` blocks, so a file reads like code."""


_Dumper.add_representer(
    str,
    lambda dumper, value: dumper.represent_scalar(
        "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None
    ),
)


def dump_style(style: QuestionStyle) -> str:
    """The style as a library file: ``styles/<subject>/<id>.yaml`` (subject left to the path)."""
    data = style.model_dump(mode="json", by_alias=True, exclude_defaults=True, exclude={"subject"})
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


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
