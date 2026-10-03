"""The question-style vocabulary (docs/QUESTION_SETUP_PLAN.md).

A *style* is a reusable way of asking: one question type, a difficulty range, one way of
checking the answer. Styles are curated code data versioned in the repo
(``app/styles/<subject>.py``), not rows: the library is content the product ships, and a
question records the style it was written in by ``QuestionRow.style_id``.

Pure data models only -- no I/O, no model calls -- so the API, the generator and the setup
suggester can all import them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Difficulty, QuestionType

#: The bounds on a suggested cell target. The suggester may not ask for fewer than one approved
#: question per cell, nor more than six.
MIN_CELL_TARGET = 1
MAX_CELL_TARGET = 6


class ExampleOption(BaseModel):
    """One choice of a choice-type example."""

    model_config = ConfigDict(frozen=True)

    text: str
    correct: bool = False


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
    #: The book section (or kind of section) the example is grounded in.
    grounding: str = ""


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
    """How many approved questions one subtopic x difficulty cell should reach."""

    subtopic_id: int
    difficulty: Difficulty
    target: int = Field(ge=MIN_CELL_TARGET, le=MAX_CELL_TARGET)


class SetupSuggestion(BaseModel):
    """What ``suggest_setup`` returns: styles per subtopic and a target per cell."""

    curriculum_version_id: int
    subject: str
    subtopics: list[SubtopicStyleSuggestion]
    cell_targets: list[CellTarget]
