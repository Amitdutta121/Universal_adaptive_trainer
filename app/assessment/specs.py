"""From a stored question to a grader call (C5): which capability grades it, with what spec.

The graders in ``graders/`` know nothing about question types or the database. Each question
type's module (``app/question_types/``, T0a) maps its stored ``content`` to one capability's
spec, plus a rewrite of the student's answer into that grader's convention (true/false is a
two-option choice, so ``"true"`` becomes index ``"0"``); this module holds the shared shapes
and the one entry point, :func:`plan_for`.

The translation is meant to change no score: ``tests/test_grader_replay.py`` replays stored
attempts through the old scorer and through this path and requires them to agree.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domain.enums import QuestionType

#: The answer as the student typed it -> the answer in the grader's convention.
AnswerRewrite = Callable[[str], str]


@dataclass(frozen=True)
class GradingPlan:
    capability: str
    spec: dict[str, Any]
    rewrite_answer: AnswerRewrite


class Unmarkable(Exception):
    """The stored content lacks what grading requires (a defect in the question)."""


def plan_for(question_type: QuestionType, content: dict, tests: object = None) -> GradingPlan:
    """The capability, spec and answer rewrite for one stored question (its type module's).

    ``tests`` is the question's ``tests`` column, used when ``content`` carries none.

    Raises:
        Unmarkable: the content is missing what this type needs, or the type is not built.
    """
    from app.question_types import get_type

    try:
        module = get_type(question_type)
    except KeyError as error:
        raise Unmarkable(f"no grading is defined for {question_type!r}") from error
    return module.grading_plan(content, tests)
