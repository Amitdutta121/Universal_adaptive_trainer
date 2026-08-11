"""Question validation boundary.

Responsibility
    Decide automatically whether a generated question is usable, producing a
    :class:`~app.domain.questions.QuestionValidationReport`.

Status
    Implemented with deterministic grounding and question-type checks. Executable
    checks use a bounded local subprocess; they do not provide a multi-tenant
    security sandbox.

Key rule
    Deterministic checks outrank LLM judgment. A question that fails a
    deterministic check (parse error, reference solution not passing its own
    tests, non-terminating execution) is invalid regardless of what an LLM
    reviewer says. LLM judgment may only add advisory, non-deterministic checks.
    This ordering is enforced by
    :attr:`~app.domain.questions.QuestionValidationReport.passed`, which ignores
    non-deterministic checks entirely.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.persistence``,
    ``app.generation.schemas``. Validation does not use an LLM.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.domain.questions import Question, QuestionValidationReport
from app.validation.service import DeterministicQuestionValidator


class QuestionValidator(Protocol):
    """Validates a single question."""

    def validate(self, question: Question) -> QuestionValidationReport: ...


def get_question_validator(session: Session | None = None) -> QuestionValidator:
    """Return the deterministic validator, optionally bound to persistence."""
    return DeterministicQuestionValidator(session)


__all__ = [
    "DeterministicQuestionValidator",
    "QuestionValidator",
    "get_question_validator",
]
