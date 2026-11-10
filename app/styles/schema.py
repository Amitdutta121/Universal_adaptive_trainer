"""The question-style vocabulary (docs/QUESTION_SETUP_PLAN.md).

A *style* is a reusable way of asking: one question type, a difficulty range, one way of
checking the answer. Styles are curated YAML versioned in the repo
(``styles/<subject>/<id>.yaml``), not rows: the library is content the product ships, and a
question records the style it was written in by ``QuestionRow.style_id``.

Pure data models only -- no I/O, no model calls -- so the API, the generator and the setup
suggester can all import them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import Difficulty, QuestionType
from app.figures.schema import ChartFigure, ComputedFigure, DiagramFigure, Figure

#: Easy and medium stay at least one. Hard may be 0 when the lesson cannot support it.
#: No cell asks for more than six.
MIN_CELL_TARGET = 1
MAX_CELL_TARGET = 6

#: Whether a style's questions carry a figure, and which kind (ADR-080). The kinds are
#: described once in ``app.assessment.catalog.FIGURE_KINDS``; ``none`` is the default.
StyleFigure = Literal["none", "diagram", "chart", "computed"]

#: The figure model a question of a style carries, per kind.
FIGURE_MODELS: dict[str, type[DiagramFigure] | type[ChartFigure] | type[ComputedFigure]] = {
    "diagram": DiagramFigure,
    "chart": ChartFigure,
    "computed": ComputedFigure,
}


class ExampleOption(BaseModel):
    """One choice of a choice-type example."""

    model_config = ConfigDict(frozen=True)

    text: str
    correct: bool = False


class ExampleTestCase(BaseModel):
    """One hidden test of a code example. Same shape as a generated question's test case
    (``app.generation.schemas.ExecutableTestCase``), which this pure module cannot import."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    stdin: str = ""
    stdout: str | None = None
    assert_code: str | None = Field(default=None, alias="assert")

    @model_validator(mode="after")
    def needs_stdout_or_assert(self) -> ExampleTestCase:
        if self.stdout is None and self.assert_code is None:
            raise ValueError("each test needs stdout or assert")
        return self


class ExampleQuestion(BaseModel):
    """One worked example shown on a style card, answer key included.

    Mirrors ``ExampleQuestion`` in ``frontend/src/app/experiments/question-setup/mock-types.ts``.
    """

    model_config = ConfigDict(frozen=True)

    prompt: str
    #: A code listing shown under the prompt.
    code: str | None = None
    #: Choice options, for choice types: ``{"text": ..., "correct": bool}``.
    options: list[ExampleOption] = Field(default_factory=list)
    #: Parsons: the solution lines in their correct order.
    lines: list[str] = Field(default_factory=list)
    #: The answer key in words: expected output, value, accepted text.
    answer: str | None = None
    #: Hidden test count, for code types graded by tests.
    tests: int | None = None
    #: Code types: the correct program, and the ``tests`` hidden tests it passes. Never shown
    #: on the card; CI runs them through the type's checks and grader (``app/styles/checks.py``).
    solution: str | None = None
    test_cases: list[ExampleTestCase] = Field(default_factory=list)
    #: The book section (or kind of section) the example is grounded in.
    grounding: str = ""
    #: The figure the student reads, for a style with a diagram or chart figure (ADR-080).
    figure: Figure | None = None


class QuestionStyle(BaseModel):
    """One style in a subject's library.

    ``id`` is stable and namespaced by subject (``py.trace_output``): it is stored on every
    question generated in this style and on every approved setup, so renaming a style must not
    change it.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=100)
    #: Subject storage key (``SubjectProfile.storage_key``), e.g. ``intro_python``.
    subject: str
    #: Short imperative name, as a professor would say it: "Predict what the code prints".
    name: str
    #: One sentence on what the student does and what it checks.
    summary: str
    question_type: QuestionType
    #: The difficulties this style can be written at; never empty.
    difficulty_range: list[Difficulty] = Field(min_length=1)
    #: How the answer is checked, in plain words: "Runs the code and compares the output".
    checked_by: str
    #: Hints for the suggester about which subtopics the style fits ("loops", "string methods").
    #: Advisory: the suggester may still pick it elsewhere, and may skip it where hinted.
    applies_to: list[str] = Field(default_factory=list)
    #: Whether each question carries a figure the student reads to answer, and which kind.
    figure: StyleFigure = "none"
    #: Exactly two examples, shown on the approve/skip card.
    examples: tuple[ExampleQuestion, ExampleQuestion]


class SubtopicStyleSuggestion(BaseModel):
    """The styles suggested for one subtopic, and why."""

    subtopic_id: int
    #: Ids from the library; the suggester validates every id against it.
    style_ids: list[str]
    #: One sentence the professor reads before approving.
    reason: str


class CellTarget(BaseModel):
    """How many approved questions one subtopic x difficulty cell should reach.

    Hard may be 0 when the lesson teaches one idea. Easy and medium stay at least one.
    """

    subtopic_id: int
    difficulty: Difficulty
    target: int = Field(ge=0, le=MAX_CELL_TARGET)

    @model_validator(mode="after")
    def easy_and_medium_need_at_least_one(self) -> CellTarget:
        if self.difficulty is not Difficulty.HARD and self.target < MIN_CELL_TARGET:
            raise ValueError(
                f"A {self.difficulty.value} cell needs at least {MIN_CELL_TARGET} question."
            )
        return self


class SetupSuggestion(BaseModel):
    """What ``suggest_setup`` returns: styles per subtopic and a target per cell."""

    curriculum_version_id: int
    subject: str
    subtopics: list[SubtopicStyleSuggestion]
    cell_targets: list[CellTarget]
