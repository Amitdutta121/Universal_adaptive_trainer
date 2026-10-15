"""The checks every recipe must pass before it ships (Task 19; run by ``tests/test_recipes.py``).

Library-wide id rules and the id lock are the style library's own (``app/styles/checks.py``),
run over ``recipes/ids.lock``. On top, each recipe must be coherent: a tool has the renderer
and input it needs, and an html recipe is loaded headless at generation time.

Every check returns problems as plain sentences naming the recipe, never raises.
"""

from __future__ import annotations

from app.domain.enums import TutorialRenderer
from app.tutorials.schema import RecipeCheck, RecipeInput, RecipeTool, TutorialRecipe


def check_recipe(recipe: TutorialRecipe) -> list[str]:
    """Problems with one recipe's combination of renderer, tool, inputs and checks."""
    problems: list[str] = []
    where = recipe.id
    if RecipeInput.SUBTOPIC not in recipe.inputs:
        problems.append(f"{where}: inputs must include 'subtopic'")
    if RecipeInput.CHUNKS not in recipe.inputs:
        problems.append(f"{where}: inputs must include 'chunks' (every block stores chunk_ids)")
    if recipe.tool is RecipeTool.PYTHON_TRACE and recipe.renderer is not TutorialRenderer.HTML:
        problems.append(f"{where}: the python_trace tool needs the html renderer (the stepper)")
    if RecipeInput.CODE in recipe.inputs and recipe.tool is not RecipeTool.PYTHON_TRACE:
        problems.append(f"{where}: a 'code' input is only read by the python_trace tool")
    if recipe.renderer is TutorialRenderer.HTML and RecipeCheck.HTML_LOADS not in recipe.checks:
        problems.append(f"{where}: an html recipe must list the 'html_loads' check")
    if RecipeCheck.TRACE_MATCHES in recipe.checks and recipe.tool is not RecipeTool.PYTHON_TRACE:
        problems.append(f"{where}: 'trace_matches' needs the python_trace tool")
    if recipe.tool is RecipeTool.PYTHON_TRACE and RecipeCheck.TRACE_MATCHES not in recipe.checks:
        problems.append(f"{where}: a python_trace recipe must list the 'trace_matches' check")
    for field in ("fits", "guidance_levels", "inputs", "checks"):
        values = getattr(recipe, field)
        if len(values) != len(set(values)):
            problems.append(f"{where}: field '{field}' repeats a value")
    return problems
