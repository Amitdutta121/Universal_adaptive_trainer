"""A course design: the curriculum, and how each subtopic is taught and checked (ADR-078)."""

from app.course_design.design import (
    CourseDesign,
    DesignCatalogue,
    DesignRecipe,
    DesignStyle,
    design_catalogue,
    design_curriculum,
    get_design,
    require_complete,
    suggest_recipes,
    suggest_styles,
)

__all__ = [
    "CourseDesign",
    "DesignCatalogue",
    "DesignRecipe",
    "DesignStyle",
    "design_catalogue",
    "design_curriculum",
    "get_design",
    "require_complete",
    "suggest_recipes",
    "suggest_styles",
]
