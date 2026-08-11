"""Orchestrate deterministic validation checks for one question."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.questions import Question, QuestionValidationReport
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner
from app.validation.shared import check_shared
from app.validation.type_checks import check_type, load_content


class DeterministicQuestionValidator:
    """Run grounding and assessment-format checks without an LLM."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def validate(self, question: Question) -> QuestionValidationReport:
        """Return the complete deterministic report for ``question``."""
        checks = check_shared(question, self._session)
        content = load_content(question)
        if content is None:
            checks.append(
                make_check(
                    "content_unreadable",
                    False,
                    "Question content is readable",
                )
            )
            return QuestionValidationReport(question_id=question.id, checks=checks)

        checks.extend(check_type(question, content, LocalCodeRunner()))
        return QuestionValidationReport(question_id=question.id, checks=checks)
