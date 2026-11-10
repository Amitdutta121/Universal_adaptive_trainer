"""The checks every style must pass before it ships (Task 17; run by ``tests/test_styles.py``).

Each example is turned into the stored ``content`` of a question of its type and put through
that type's own ``authoring_checks`` and its grader's ``check_spec`` -- the same two gates a
generated question passes -- so a style card can never show an example the product would reject.
Library-wide: ids are namespaced and unique, and ``styles/ids.lock`` keeps every id ever shipped,
because questions and approved setups store them.

Every check returns problems as plain sentences naming the style (and example), never raises.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from app.assessment.specs import Unmarkable
from app.domain.enums import QuestionType
from app.figures.schema import figure_problems
from app.styles.schema import ExampleQuestion, QuestionStyle
from app.validation.runner import LocalCodeRunner
from graders import SpecError, get_grader

#: ``<prefix>.<name>``: one prefix per subject (``py``), a snake_case name.
ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$")


class HasId(Protocol):
    """A style or a tutorial recipe: anything the id checks look at."""

    @property
    def id(self) -> str: ...


_EXECUTABLE = {QuestionType.CODE_COMPLETION, QuestionType.DEBUGGING, QuestionType.CODING}


def example_content(style: QuestionStyle, example: ExampleQuestion) -> dict[str, Any]:
    """The stored ``content`` a question of the style's type would have for this example.

    Examples carry no separate explanation; the answer key in words stands in for it.
    """
    kind = style.question_type
    content: dict[str, Any] = {"prompt": example.prompt, "explanation": example.answer}
    if example.figure is not None:
        content["figure"] = example.figure.model_dump(mode="json")
    if kind is QuestionType.MULTIPLE_CHOICE:
        content["options"] = [option.text for option in example.options]
        correct = [n for n, option in enumerate(example.options) if option.correct]
        content["correct_option_index"] = correct[0] if len(correct) == 1 else None
    elif kind is QuestionType.TRUE_FALSE:
        correct = [option.text.strip().lower() for option in example.options if option.correct]
        content["correct_answer"] = (
            {"true": True, "false": False}.get(correct[0]) if correct else None
        )
    elif kind is QuestionType.OUTPUT_PREDICTION:
        content["code"] = example.code
        content["expected_output"] = example.answer
    elif kind is QuestionType.PARSONS:
        content["blocks"] = [
            {"id": str(n), "text": line.strip(), "indent": (len(line) - len(line.lstrip())) // 4}
            for n, line in enumerate(example.lines)
        ]
        content["correct_order"] = [str(n) for n in range(len(example.lines))]
    elif kind in _EXECUTABLE:
        if kind is not QuestionType.CODING:
            content["code"] = example.code
        content["reference_solution"] = example.solution
        content["tests"] = [case.model_dump(by_alias=True) for case in example.test_cases]
    return content


def check_example(
    style: QuestionStyle, index: int, runner: LocalCodeRunner | None = None
) -> list[str]:
    """Problems with one example: its type's authoring checks, then its grader's spec check."""
    from app.question_types import get_type

    example = style.examples[index]
    where = f"{style.id} example {index + 1}"
    problems: list[str] = []
    if style.question_type in _EXECUTABLE:
        if example.solution is None or not example.test_cases:
            return [
                f"{where}: a {style.question_type.value} example needs a solution and test_cases"
            ]
        if example.tests != len(example.test_cases):
            problems.append(
                f"{where}: tests is {example.tests} "
                f"but there are {len(example.test_cases)} test_cases"
            )
    try:
        module = get_type(style.question_type)
    except KeyError:
        return [f"{where}: question type {style.question_type.value} has no module"]
    problems += [f"{where}: {problem}" for problem in example_figure_problems(style, example)]
    content = example_content(style, example)
    for check in module.authoring_checks(content, runner or LocalCodeRunner()):
        if not check.passed:
            detail = f" ({check.evidence})" if check.evidence else ""
            problems.append(f"{where}: fails '{check.name}'{detail}")
    try:
        plan = module.grading_plan(content, None)
        issues = get_grader(plan.capability).check_spec(plan.spec)
    except (Unmarkable, SpecError) as error:
        problems.append(f"{where}: cannot be graded: {error}")
    else:
        problems.extend(f"{where}: grader says {issue.code}: {issue.message}" for issue in issues)
    return problems


def example_figure_problems(style: QuestionStyle, example: ExampleQuestion) -> list[str]:
    """Why an example's figure does not fit its style, or cannot be drawn; ``[]`` if fine.

    A diagram or chart style's examples each show that kind of figure, drawable
    (:func:`app.figures.figure_problems`). A computed figure is drawn by a program when
    questions are generated, so its examples carry none; neither does a style without a figure.
    """
    figure = example.figure
    if style.figure in ("diagram", "chart"):
        if figure is None:
            return [f"a {style.figure} style's example needs a {style.figure} figure"]
        if figure.kind != style.figure:
            return [f"the figure is a {figure.kind}, but the style asks for a {style.figure}"]
        return [f"figure: {problem}" for problem in figure_problems(figure)]
    if figure is None:
        return []
    if style.figure == "computed":
        return ["a computed figure is drawn when questions are generated; examples carry none"]
    return [f"the style has no figure, so its examples carry none (found a {figure.kind})"]


def check_ids(libraries: Mapping[str, Sequence[HasId]]) -> list[str]:
    """Ids match ``<prefix>.<name>``, one prefix per subject, no id or prefix shared."""
    problems: list[str] = []
    owner: dict[str, str] = {}
    prefix_owner: dict[str, str] = {}
    for subject, styles in libraries.items():
        prefixes = set()
        for style in styles:
            if not ID_PATTERN.match(style.id):
                problems.append(
                    f"{subject}/{style.id}: id must look like '<prefix>.<snake_case_name>'"
                )
                continue
            if style.id in owner:
                problems.append(f"{style.id}: duplicate id, in {owner[style.id]} and {subject}")
            owner.setdefault(style.id, subject)
            prefixes.add(style.id.split(".", 1)[0])
        if len(prefixes) > 1:
            problems.append(f"{subject}: ids use several prefixes ({', '.join(sorted(prefixes))})")
        for prefix in prefixes:
            if prefix_owner.setdefault(prefix, subject) != subject:
                problems.append(
                    f"{subject}: prefix '{prefix}' already belongs to {prefix_owner[prefix]}"
                )
    return problems


def read_lock(path: Path) -> list[str]:
    """The locked ids, one ``<subject>/<id>`` per line; ``#`` starts a comment."""
    lines = (
        line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()
    )
    return [line for line in lines if line]


def check_lock(
    libraries: Mapping[str, Sequence[HasId]],
    locked: Iterable[str],
    *,
    lock: str = "styles/ids.lock",
    noun: str = "style",
) -> list[str]:
    """Every locked id still ships; every shipped id is locked.

    Also run over the tutorial recipes (``recipes/ids.lock``), which follow the same rule.
    """
    shipped = {f"{subject}/{item.id}" for subject, items in libraries.items() for item in items}
    locked = set(locked)
    problems = [
        f"{entry}: in {lock} but its {noun} file is gone. Ids are stored, so a {noun} is never "
        f"removed or renamed: restore the file (a new id is a new {noun})"
        for entry in sorted(locked - shipped)
    ]
    problems.extend(
        f"{entry}: new {noun} id not in {lock}; add the line '{entry}' to it"
        for entry in sorted(shipped - locked)
    )
    return problems
