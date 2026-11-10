"""Deterministic checks for each supported assessment format (each type module's own)."""

from __future__ import annotations

from app.domain.questions import Question, QuestionCheck
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner


def check_type(
    question: Question,
    content: dict,
    runner: LocalCodeRunner,
) -> list[QuestionCheck]:
    """Run the checks belonging to the question's assessment format."""
    if question.question_type is None:
        return []

    from app.question_types import get_type

    try:
        module = get_type(question.question_type)
    except KeyError:
        return [
            make_check(
                "question_type_built",
                False,
                "Question type is built",
                f"{question.question_type.value} has no module in app/question_types.",
            )
        ]
    return [*module.authoring_checks(content, runner), *figure_checks(content)]


def figure_checks(content: dict) -> list[QuestionCheck]:
    """Whether the question's figure can be drawn, when it has one (ADR-080); any type.

    The problems are the evidence, so a generation retry tells the model what to fix.
    """
    if content.get("figure") is None:
        return []
    from app.figures import figure_problems

    problems = figure_problems(content["figure"])
    return [
        make_check(
            "figure_drawable",
            not problems,
            "The figure can be drawn",
            " ".join(f"{problem.rstrip('.')}." for problem in problems) or None,
        )
    ]
