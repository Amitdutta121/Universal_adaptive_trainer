"""The grader contract (C0). Frozen: work packages implement it, they do not change it.

A **grader** implements one capability (``structured.choice``, ``code.python.tests``, ...). It is
given a question's **spec** -- the per-question settings that capability needs, validated by the
grader's own pydantic ``spec_model`` -- and a student's **answer** as text.

- ``check_spec`` answers "can this question be graded?": the spec is well-formed and its
  reference answer scores full marks. It returns issues; an empty list means gradable.
- ``grade`` scores one answer, 0.0 to 1.0. An answer that cannot be read is a *wrong* answer
  (score 0 with ``format_error`` set), never an exception. A spec that cannot be graded at all
  raises :class:`SpecError` -- that question should not have been served.

This package knows nothing about the application: no database, no LLM, no ``app`` import
(``tests/graders/test_isolation.py`` enforces it).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class SpecError(Exception):
    """The question's spec cannot be graded at all (a defect in the question, not the answer)."""


@dataclass(frozen=True)
class TestResult:
    """One test inside a graded answer (code graders); other graders return none."""

    __test__ = False  # not a pytest test class

    name: str
    passed: bool
    points: float
    max_points: float
    message: str | None = None


@dataclass(frozen=True)
class GradeResult:
    """What one answer was worth."""

    #: 0.0 to 1.0.
    score: float
    tests: tuple[TestResult, ...] = ()
    #: Shown to the student afterwards.
    feedback: str | None = None
    #: Set when the answer could not be read; the score is then 0.
    format_error: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be within 0..1, got {self.score}")


@dataclass(frozen=True)
class SpecIssue:
    """Why a spec is not gradable. ``code`` is stable; ``message`` is for people."""

    code: str
    message: str


@runtime_checkable
class Grader(Protocol):
    capability: str
    version: str
    spec_model: type[BaseModel]

    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]: ...

    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult: ...


def parse_spec(model: type[BaseModel], spec: Mapping[str, Any]) -> BaseModel:
    """Validate a raw spec against a grader's model, raising :class:`SpecError` on failure.

    Shared so every grader words a broken spec the same way.
    """
    from pydantic import ValidationError

    try:
        return model.model_validate(dict(spec))
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in issue['loc']) or 'spec'}: {issue['msg']}"
            for issue in error.errors()[:6]
        )
        raise SpecError(problems) from error
