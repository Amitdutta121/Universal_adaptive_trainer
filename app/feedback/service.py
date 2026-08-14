"""Write path for professor approve / reject / edit reviews."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.enums import QuestionStatus, RejectionReason, ReviewDecision
from app.domain.questions import Question, apply_professor_edit
from app.errors import DomainRuleError
from app.persistence.models import ProfessorReviewRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository

_EDITABLE = ("prompt", "reference_solution", "tests")


def _norm(value: str | None) -> str:
    return "" if value is None else value


def submit_review(
    session: Session,
    *,
    question_id: int,
    decision: ReviewDecision,
    reasons: list[RejectionReason] | None = None,
    comment: str | None = None,
    prompt: str | None = None,
    reference_solution: str | None = None,
    tests: str | None = None,
    professor_id: int | None = None,
) -> ProfessorReviewRow:
    """Append a professor review and update the question's usable status.

    Edit updates current question fields but never touches ``original_*``.
    ``changed_fields`` are derived here by comparing submitted values to the
    persisted question, never trusted from the client.
    """
    question = QuestionRepository(session).get(question_id)
    reason_list = list(reasons or [])

    edited_prompt: str | None = None
    edited_reference_solution: str | None = None
    edited_tests: str | None = None
    changed_fields: list[str] = []

    if decision is ReviewDecision.APPROVE:
        reason_list = []
        question.status = QuestionStatus.APPROVED
    elif decision is ReviewDecision.REJECT:
        if not reason_list:
            raise DomainRuleError("Reject requires at least one structured reason.")
        question.status = QuestionStatus.REJECTED
    elif decision is ReviewDecision.EDIT:
        if prompt is None or reference_solution is None or tests is None:
            raise DomainRuleError(
                "Edit requires prompt, reference_solution, and tests "
                "(use empty string when unused)."
            )
        if not prompt.strip():
            raise DomainRuleError("Edited prompt must not be empty.")

        edited_prompt = prompt
        edited_reference_solution = reference_solution
        edited_tests = tests
        current = {
            "prompt": _norm(question.prompt),
            "reference_solution": _norm(question.reference_solution),
            "tests": _norm(question.tests),
        }
        submitted = {
            "prompt": edited_prompt,
            "reference_solution": edited_reference_solution,
            "tests": edited_tests,
        }
        changed_fields = [name for name in _EDITABLE if current[name] != submitted[name]]
        if not changed_fields:
            raise DomainRuleError("Edit requires at least one changed field.")

        before_edit = Question.model_validate(question)
        edited_question = apply_professor_edit(
            before_edit,
            prompt=edited_prompt,
            reference_solution=edited_reference_solution,
            tests=edited_tests,
        )
        # Persist the generated text before overwriting it. ``Question`` seeds
        # ``original_*`` on construction, but only on the domain copy; a row that
        # reached the database without them would otherwise lose the generated
        # version here, and "generated vs. accepted" (ADR-002) is exactly what a
        # judge repair and a generator refresh both read.
        if question.original_prompt is None:
            question.original_prompt = before_edit.original_prompt
        if question.original_reference_solution is None:
            question.original_reference_solution = before_edit.original_reference_solution
        if question.original_tests is None:
            question.original_tests = before_edit.original_tests
        question.prompt = edited_question.prompt
        question.reference_solution = edited_question.reference_solution
        question.tests = edited_question.tests
        question.updated_at = edited_question.updated_at
        question.status = QuestionStatus.APPROVED
    else:
        raise DomainRuleError(f"Unsupported review decision: {decision}")

    review = ProfessorReviewRow(
        question_id=question.id,
        decision=decision,
        reasons=reason_list,
        comment=comment,
        edited_prompt=edited_prompt,
        edited_reference_solution=edited_reference_solution,
        edited_tests=edited_tests,
        changed_fields=changed_fields,
        professor_id=professor_id,
        reviewed_generator_name=question.generator_name,
        reviewed_generator_version=question.generator_version,
    )
    return ProfessorReviewRepository(session).add(review)
