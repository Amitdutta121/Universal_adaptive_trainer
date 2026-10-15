"""The tutorial-recipe vocabulary (Phase 5, Task 19).

A *recipe* is a reusable way of teaching one kind of content: which trusted renderer draws it,
what the model is asked to write, which guidance levels it supports and, for executable content,
which tool supplies the truth (``python_trace``) so the model never has to. Recipes are curated
YAML in the repo (``recipes/<subject>/<id>.yaml``), like question styles; a generated block
stores the ``recipe_id`` it came from.

Pure data models only -- no I/O, no model calls.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import GuidanceLevel, TutorialRenderer


class ContentKind(StrEnum):
    """What a subtopic's material is mostly about; the composer matches it to ``fits``."""

    #: What a piece of code does when it runs.
    CODE = "code"
    #: An idea or definition.
    CONCEPT = "concept"
    #: Steps or stages in order, or how ideas connect.
    PROCESS = "process"
    #: A common wrong belief and its correction.
    MISCONCEPTION = "misconception"


class RecipeInput(StrEnum):
    """What the generator hands the model besides the recipe's prompt."""

    SUBTOPIC = "subtopic"
    #: Excerpts of the retrieved chunks; every block stores their ids.
    CHUNKS = "chunks"
    #: A code snippet given by the caller (e.g. the question a student got wrong). Without it,
    #: a code recipe's model writes the snippet itself.
    CODE = "code"


class RecipeTool(StrEnum):
    """A tool whose output a block embeds as-is (Task 20)."""

    PYTHON_TRACE = "python_trace"


class RecipeCheck(StrEnum):
    """A generation-time check a block of the recipe must pass (Task 23)."""

    #: Loads the html headless; a console error fails it.
    HTML_LOADS = "html_loads"
    #: Clicks through a stepper and compares every displayed step to the recorded trace.
    TRACE_MATCHES = "trace_matches"


class TutorialRecipe(BaseModel):
    """One recipe in a subject's library.

    ``id`` is stable and namespaced by subject (``py.code_trace_stepper``): blocks store it and
    per-recipe stats key on it, so it is never renamed.
    """

    model_config = ConfigDict(frozen=True, use_enum_values=False)

    id: str = Field(min_length=1, max_length=100)
    #: Subject storage key (``SubjectProfile.storage_key``), e.g. ``intro_python``.
    subject: str
    #: Short name, as a professor would say it: "Step through the code".
    name: str
    #: One sentence on what the student sees.
    summary: str
    renderer: TutorialRenderer
    #: The model's instructions for this recipe. The generator adds the subtopic, the guidance
    #: level and the chunk excerpts; the prompt says what to write and how.
    prompt: str = Field(min_length=1)
    #: The kinds of content this recipe teaches well; never empty.
    fits: list[ContentKind] = Field(min_length=1)
    #: The guidance levels this recipe can be written at; never empty.
    guidance_levels: list[GuidanceLevel] = Field(min_length=1)
    inputs: list[RecipeInput] = Field(default_factory=lambda: [RecipeInput.SUBTOPIC])
    tool: RecipeTool | None = None
    checks: list[RecipeCheck] = Field(default_factory=list)
