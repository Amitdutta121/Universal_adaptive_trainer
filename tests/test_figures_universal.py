"""Universality rule 1 (docs/FIGURE_QUESTIONS_MILESTONES.md): the figure code names no subject."""

from __future__ import annotations

import re
from pathlib import Path

from app.assessment.catalog import SUBJECTS

FIGURES = Path(__file__).resolve().parent.parent / "app" / "figures"

SUBJECT_WORDS = (
    "python",
    "physics",
    "biology",
    "chemistry",
    "statistics",
    "economics",
    "mathematics",
    "calculus",
    "algebra",
    "programming",
    "machine learning",
    "data science",
    "genetics",
    "finance",
)


def test_the_figure_package_names_no_subject_or_preset() -> None:
    files = sorted(FIGURES.rglob("*.py"))
    assert files, "app/figures is missing"
    banned = {preset.id for preset in SUBJECTS if preset.id != "custom"} | set(SUBJECT_WORDS)
    found = []
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for word in banned:
            if re.search(rf"\b{re.escape(word.lower())}\b", text):
                found.append(f"{path.name}: {word}")
    assert found == []


def test_the_figure_package_imports_nothing_layer_specific() -> None:
    allowed = re.compile(r"^(app\.figures|app\.config|app\.domain)(\.|$)")
    for path in FIGURES.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*(?:from|import)\s+(app\.[\w.]+)", line)
            if match:
                assert allowed.match(match.group(1)), f"{path.name} imports {match.group(1)}"
