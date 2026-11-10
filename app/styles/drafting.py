"""Drafting a question style from a professor's words, for the course agent.

The model writes the fields of a :class:`~app.styles.schema.QuestionStyle`; the id is built here
from the subject's prefix, never trusted. The draft then goes through the same checks a saved
course style passes (:func:`app.styles.library.add_course_style`): ids, the course's question
types, and each example through its type's authoring checks and grader. An invalid draft gets
one repair retry naming the problems. Saves nothing: ``save_style`` does, on approval.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.assessment.catalog import FIGURE_KINDS_BY_ID, built_figure_kinds
from app.domain.enums import Difficulty, QuestionType
from app.errors import MalformedModelOutputError
from app.figures.schema import MERMAID_KINDS
from app.llm import ChatTurn, StructuredLLMClient
from app.styles.checks import check_example, check_ids
from app.styles.library import styles_for
from app.styles.loader import dump_style
from app.styles.schema import ExampleQuestion, QuestionStyle, StyleFigure
from app.subjects import SubjectProfile

MAX_ATTEMPTS = 2


class StyleDraft(BaseModel):
    """What the model writes; :func:`draft_style` turns it into a :class:`QuestionStyle`."""

    slug: str = Field(description="snake_case, at most 40 characters; the id is <prefix>.<slug>")
    name: str = Field(description="Short imperative, as a professor would say it")
    summary: str = Field(description="One sentence: what the student does and what it checks")
    question_type: QuestionType
    difficulty_range: list[Difficulty] = Field(min_length=1)
    checked_by: str = Field(description="How the answer is checked, in plain words")
    applies_to: list[str] = Field(
        default_factory=list, description="Kinds of subtopic the style fits"
    )
    figure: StyleFigure = Field(
        default="none",
        description="none, or the kind of figure each question shows the student to read",
    )
    examples: list[ExampleQuestion] = Field(description="Exactly two real, correct examples")


_DIAGRAM_KINDS = ", ".join(kind for kind in MERMAID_KINDS if not kind.startswith("stateDiagram"))

#: How a style asks for a figure (ADR-080). Subject-neutral: the material decides, not the
#: subject (``tests/test_figure_styles.py`` scans it).
FIGURE_SYSTEM = f"""\
`figure` says whether each question shows the student a figure to read. Keep `none` unless the
answer depends on reading one. Choose a figure when the material the style asks about is
something to look at: a structure, a process or flow, states and the transitions between them, a
cycle, a dataset, a grid. A style that asks to recall a definition, a fact or a term keeps
`none`. Use only the figure kinds listed with the request.
- diagram: each example's `figure` is {{"kind": "diagram", "source": <Mermaid source>, "alt",
  "caption"}}. The source starts with one of: {_DIAGRAM_KINDS}. Draw states and transitions as a
  flowchart with labelled edges, not a stateDiagram. No click, init directives, links or
  scripts; Mermaid has no escapes, so write A["label"] and #quot; for a quote in a label.
- chart: each example's `figure` is {{"kind": "chart", "chart": {{"type": bar | line | pie |
  doughnut | scatter, "data": {{"labels": [...], "datasets": [{{"label", "data": [one number per
  label]}}]}}, "x_title", "y_title"}}, "alt", "caption"}}. A scatter chart has no labels and its
  data are {{"x", "y"}} points.
- computed: a program draws the figure when questions are generated, so the examples carry no
  `figure`.
The figure is needed to answer and does not give the answer away. Label every node, axis and
series. `alt` says in words everything the figure shows. Without a figure, examples carry none."""

SYSTEM = (
    """\
You design question styles for an adaptive assessment system. A style is one reusable way of
asking: one question type, the difficulties it can be written at, and how the answer is checked.
A generator later writes many questions in the style for each subtopic of the course, so the
style describes a kind of question, not one question.

Write exactly two examples. They are shown to the professor before approving, and they must be
real, correct questions that pass the type's own checks:
- multiple_choice: `options` with exactly one `correct: true`; `answer` explains it.
- true_false: options `True` and `False`, exactly one correct.
- short_answer: `answer` is the accepted answer.
- output_prediction: `code`, and `answer` is exactly what the code prints.
- parsons: `lines` are the solution's lines in the correct order, 4 spaces per indent level.
- code_completion, debugging, coding: `solution` is the correct Python program and
  `test_cases` each have `assert` (and/or `stdin` / `stdout`); `tests` equals their count.
  For debugging, `code` is the buggy program and must fail at least one test.
Use only the question types the course allows. `grounding` names the kind of book section the
example comes from. Keep names short and summaries to one sentence.

"""
    + FIGURE_SYSTEM
)


@dataclass(frozen=True)
class StyleDraftResult:
    yaml: str
    #: Empty when the draft passes every check; otherwise why not, after the repair retry.
    problems: list[str]
    #: The parsed style, for showing it as a card; ``None`` when the fields did not validate.
    style: QuestionStyle | None = None


def id_prefix(profile: SubjectProfile, existing: list[QuestionStyle]) -> str:
    """The prefix every style of this course uses: the library's (``py``), or the course's own.

    A course with no styles yet gets ``c<course id>`` for a custom subject (it owns its key) and
    the letters of the preset id otherwise (``physics``, ``mlllms``).
    """
    if existing:
        return existing[0].id.split(".", 1)[0]
    if profile.subject_id == "custom" and profile.course_id is not None:
        return f"c{profile.course_id}"
    return re.sub(r"[^a-z0-9]", "", profile.subject_id.lower()) or "s"


def _style_id(prefix: str, slug: str) -> str:
    clean = slug.strip().lower().removeprefix(f"{prefix}.")
    clean = re.sub(r"[^a-z0-9]+", "_", clean).strip("_")[:60] or "style"
    if not clean[0].isalpha():
        clean = f"s_{clean}"[:60]
    return f"{prefix}.{clean}"


def _prompt(
    profile: SubjectProfile,
    existing: list[QuestionStyle],
    description: str,
    current: str | None,
) -> str:
    allowed = ", ".join(profile.question_types) or "any"
    figures = "; ".join(f"{kind.id} ({kind.description})" for kind in built_figure_kinds())
    parts = [f"The course's question types: {allowed}.", f"Figure kinds: none; {figures}."]
    if existing:
        shown = "\n---\n".join(dump_style(style) for style in existing[:2])
        names = "; ".join(f"{style.id}: {style.name}" for style in existing)
        parts.append(f"Styles this course already has (do not repeat them): {names}")
        parts.append(f"Two of them in full, for their shape:\n{shown}")
    if current:
        parts.append(f"The style to revise:\n{current}")
        parts.append(f"Revise it as the professor asks: {description}")
    else:
        parts.append(f"Design a new style for what the professor asks: {description}")
    return "\n\n".join(parts)


def _problems(
    style: QuestionStyle, profile: SubjectProfile, existing: list[QuestionStyle]
) -> list[str]:
    problems: list[str] = []
    if style.id in {s.id for s in existing}:
        problems.append(f"the id {style.id} is taken; choose another slug")
    if profile.question_types and style.question_type.value not in profile.question_types:
        allowed = ", ".join(profile.question_types)
        problems.append(f"question type {style.question_type.value} is not one of: {allowed}")
    if style.figure != "none" and not FIGURE_KINDS_BY_ID[style.figure].built:
        problems.append(f"{style.figure} figures cannot be generated yet; choose another kind")
    problems += check_ids({profile.storage_key: [*existing, style]})
    problems += [p for n in range(len(style.examples)) for p in check_example(style, n)]
    return problems


def draft_style(
    session: Session,
    profile: SubjectProfile,
    client: StructuredLLMClient,
    description: str,
    current_yaml: str | None = None,
) -> StyleDraftResult:
    """A style drafted (or ``current_yaml`` revised) from the professor's words. Saves nothing.

    The returned YAML is what ``save_style`` takes. When ``problems`` is not empty the draft
    still failed after the repair retry; it comes back anyway so it can be fixed by hand.
    """
    existing = styles_for(session, profile)
    prefix = id_prefix(profile, existing)
    if current_yaml:
        # A revision keeps its own id, so drop it from the "taken" list.
        existing = [s for s in existing if f"id: {s.id}" not in current_yaml]
    prompt = _prompt(profile, existing, description, current_yaml)
    asking = prompt
    history: list[ChatTurn] = []
    last_yaml = current_yaml or ""
    problems: list[str] = []
    style: QuestionStyle | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            draft = client.complete_structured(
                system=SYSTEM,
                prompt=asking,
                response_model=StyleDraft,
                **({"history": tuple(history)} if history else {}),
            )
        except MalformedModelOutputError as exc:
            problems = [f"the reply did not match the requested structure ({exc.detail or ''})"]
            asking = f"{prompt}\n\nYour last reply could not be read: {problems[0]}. Try again."
            continue
        data = draft.model_dump(mode="json", by_alias=True, exclude={"slug"})
        try:
            style = QuestionStyle.model_validate(
                {**data, "id": _style_id(prefix, draft.slug), "subject": profile.storage_key}
            )
        except ValidationError as exc:
            style = None
            problems = [
                f"{'.'.join(str(part) for part in error['loc']) or 'style'}: {error['msg']}"
                for error in exc.errors()
            ]
            last_yaml = json.dumps(data, indent=2)
        else:
            problems = _problems(style, profile, existing)
            last_yaml = dump_style(style)
        if not problems:
            break
        history = [("user", prompt), ("assistant", json.dumps(draft.model_dump(mode="json")))]
        listed = "\n".join(f"- {problem}" for problem in problems)
        asking = f"That style cannot be used:\n{listed}\nWrite it again, fixing these."
    return StyleDraftResult(yaml=last_yaml, problems=problems, style=style)
