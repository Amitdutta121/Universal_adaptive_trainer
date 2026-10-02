"""The question-type seam (phase 2, T0a). Frozen once wave 0 lands.

A question type is one module under :mod:`app.question_types` implementing
:class:`QuestionTypeModule`. Everything that differs between types lives there -- what the
LLM must return, the shipped instruction, the legacy columns, how a stored question is graded,
the type-only authoring checks and what a student may see -- so a new type is a new file, and
generation, validation, scoring and the student API stay type-agnostic.

Allowed dependencies (to keep the import graph acyclic): ``app.domain``, ``app.assessment.specs``
(grading plans), ``app.validation.report`` / ``app.validation.runner`` (checks and the code
runner), ``app.generation.schemas`` (draft base classes). Never ``app.generation.base`` /
``service`` or the web layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.assessment.specs import GradingPlan
    from app.domain.enums import QuestionKind, QuestionType
    from app.domain.questions import QuestionCheck
    from app.generation.schemas import TaxonomyClaim
    from app.validation.runner import LocalCodeRunner


@dataclass(frozen=True)
class DraftColumns:
    """The legacy question columns a draft fills (the whole draft also goes to ``content``)."""

    prompt: str
    #: What a reviewer sees as "the answer": the right option's text, the expected output, ...
    reference_solution: str | None
    #: JSON text of executable test cases, for types that have them.
    tests: str | None


@dataclass(frozen=True)
class StudentView:
    """What a student may see of a stored question besides its prompt.

    A whitelist: anything not named here is never published, because ``content`` holds the
    answer. ``blocks`` items are ``{"id", "text", "indent"}``.
    """

    options: list[str] | None = None
    code: str | None = None
    blocks: list[dict[str, Any]] | None = None
    #: A short instruction on the answer's form, e.g. "Give a number with its unit (m/s)."
    answer_hint: str | None = None


@runtime_checkable
class QuestionTypeModule(Protocol):
    question_type: QuestionType
    kind: QuestionKind
    #: The structured-output schema the LLM must return.
    draft_model: type[TaxonomyClaim]
    #: The shipped type instruction; a professor's learned instruction replaces it (ADR-033).
    instruction: str

    def columns_from_draft(self, draft: TaxonomyClaim) -> DraftColumns: ...

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        """Capability, grader spec and answer rewrite. Raises ``Unmarkable``."""
        ...

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        """Deterministic checks for a newly generated question of this type."""
        ...

    def student_view(self, content: dict, *, seed: int) -> StudentView: ...
