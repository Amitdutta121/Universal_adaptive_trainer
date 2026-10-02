"""The one generic authoring check, ``gradable`` (phase 2, C8).

A question is gradable when its type module can build a grading plan from the stored content and
the plan's grader accepts the spec (``check_spec``: well-formed, the reference scores full
marks). It uses only the two registries -- :func:`app.question_types.get_type` and
:func:`graders.get_grader` -- so a type added later is checked with no change here.

Type modules keep only the checks that are not about grading (the buggy code must fail, the code
parses, an explanation is present, ...).
"""

from __future__ import annotations

from app.assessment.specs import Unmarkable
from app.domain.questions import Question, QuestionCheck
from app.errors import CodeExecutionUnavailableError
from app.validation.report import make_check
from app.validation.runner import EVIDENCE_LIMIT
from graders import ExecutorError, SpecError, get_grader

CHECK_NAME = "gradable"
_DETAIL = "Question can be graded"


def check_gradable(question: Question, content: dict) -> list[QuestionCheck]:
    """``[gradable]`` for a built type; ``[]`` when there is no type or it is not built.

    An unbuilt type is already reported by ``question_type_built`` (see
    :func:`app.validation.type_checks.check_type`).

    Raises:
        CodeExecutionUnavailableError: the executor could not run the reference at all. An
            outage says nothing about the question, so it is never a failed check.
    """
    if question.question_type is None:
        return []

    from app.question_types import get_type

    try:
        module = get_type(question.question_type)
    except KeyError:
        return []

    try:
        plan = module.grading_plan(content, question.tests)
    except Unmarkable as error:
        return [_failed(f"Cannot be graded: {error}.")]

    try:
        grader = get_grader(plan.capability)
    except KeyError:
        return [_failed(f"No grader is built for {plan.capability!r}.")]

    try:
        issues = grader.check_spec(plan.spec)
    except SpecError as error:
        return [_failed(str(error))]
    except ExecutorError as error:
        raise CodeExecutionUnavailableError(
            "Code could not be run right now, so this question could not be checked.",
            detail=str(error),
        ) from error

    if issues:
        evidence = "\n".join(f"{issue.code}: {issue.message}" for issue in issues)
        return [_failed(evidence)]
    return [make_check(CHECK_NAME, True, _DETAIL)]


def _failed(evidence: str) -> QuestionCheck:
    return make_check(CHECK_NAME, False, _DETAIL, evidence[:EVIDENCE_LIMIT])
