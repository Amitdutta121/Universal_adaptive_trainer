"""Load the recipe library from YAML (``recipes/<subject>/<id>.yaml``).

Same layout and rules as the style library (``app/styles/loader.py``): one file per recipe, the
subject from the directory and the id from the file name, and a bad file fails loudly with its
path and field, because blocks store recipe ids.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.tutorials.schema import TutorialRecipe

#: Repo-root ``recipes/``, beside ``styles/``.
RECIPES_DIR = Path(__file__).resolve().parents[2] / "recipes"


class RecipeFileError(ValueError):
    """A recipe file that cannot be loaded. The message names the file and the field."""


def load_recipe_file(path: Path, subject: str) -> TutorialRecipe:
    source = str(path)
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RecipeFileError(f"{source}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise RecipeFileError(f"{source}: expected a mapping of recipe fields at the top level")
    for field, value, origin in (
        ("subject", subject, "the directory"),
        ("id", path.stem, "the file name"),
    ):
        if data.setdefault(field, value) != value:
            raise RecipeFileError(
                f"{source}: field '{field}' is {data[field]!r} but must be {value!r} ({origin})"
            )
    try:
        return TutorialRecipe.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"field '{'.'.join(str(part) for part in error['loc'])}': {error['msg']}"
            for error in exc.errors()
        )
        raise RecipeFileError(f"{source}: {problems}") from exc


def load_subject(directory: Path) -> list[TutorialRecipe]:
    """Every recipe of one subject directory, sorted by id."""
    return [load_recipe_file(path, directory.name) for path in sorted(directory.glob("*.yaml"))]


def load_recipes(root: Path = RECIPES_DIR) -> dict[str, list[TutorialRecipe]]:
    """Every subject's recipes under ``root``, keyed by subject storage key."""
    if not root.is_dir():
        return {}
    return {
        directory.name: load_subject(directory)
        for directory in sorted(root.iterdir())
        if directory.is_dir()
    }
