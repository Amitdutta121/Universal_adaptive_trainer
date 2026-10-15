"""Question styles: the curated library and the setup suggester (docs/QUESTION_SETUP_PLAN.md)."""

from app.styles.library import (
    add_course_style,
    course_styles,
    get_library,
    styles_for,
    suggest_setup,
)
from app.styles.schema import (
    MAX_CELL_TARGET,
    MIN_CELL_TARGET,
    CellTarget,
    ExampleOption,
    ExampleQuestion,
    QuestionStyle,
    SetupSuggestion,
    SubtopicStyleSuggestion,
)

__all__ = [
    "MAX_CELL_TARGET",
    "MIN_CELL_TARGET",
    "CellTarget",
    "ExampleOption",
    "ExampleQuestion",
    "QuestionStyle",
    "SetupSuggestion",
    "SubtopicStyleSuggestion",
    "add_course_style",
    "course_styles",
    "get_library",
    "styles_for",
    "suggest_setup",
]
