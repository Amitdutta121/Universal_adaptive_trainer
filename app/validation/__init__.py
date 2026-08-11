"""Question validation boundary.

Responsibility
    Decide automatically whether a generated question is usable, producing a
    :class:`~app.domain.questions.QuestionValidationReport`.

Status
    **Not implemented in this task.** Only the seam exists. Sandboxed execution
    of model-written code is a security-sensitive design step of its own.

Key rule
    Deterministic checks outrank LLM judgment. A question that fails a
    deterministic check (parse error, reference solution not passing its own
    tests, non-terminating execution) is invalid regardless of what an LLM
    reviewer says. LLM judgment may only add advisory, non-deterministic checks.
    This ordering is enforced by
    :attr:`~app.domain.questions.QuestionValidationReport.passed`, which ignores
    non-deterministic checks entirely.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.llm``.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.questions import Question, QuestionValidationReport
from app.errors import FeatureNotAvailableError

#: Deterministic checks that must exist before validation can be trusted.
PLANNED_DETERMINISTIC_CHECKS = (
    "prompt_non_empty",
    "solution_parses",
    "solution_passes_own_tests",
    "tests_are_non_trivial",
    "execution_within_timeout",
)


class QuestionValidator(Protocol):
    """Validates a single question."""

    def validate(self, question: Question) -> QuestionValidationReport: ...


class NullQuestionValidator:
    """Placeholder validator.

    Raises instead of returning an empty passing report -- an empty report would
    read as "validated" when nothing was checked.
    """

    def validate(self, question: Question) -> QuestionValidationReport:
        raise FeatureNotAvailableError(
            "Automatic question validation is not implemented yet.",
            detail="Deterministic checks require a sandboxed execution design.",
        )


def get_question_validator() -> QuestionValidator:
    """Return the configured validator. Currently always the null implementation."""
    return NullQuestionValidator()
