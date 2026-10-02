"""Code completion: finish the given code; scored by its tests (``code.python.tests``)."""

from __future__ import annotations

from app.domain.enums import QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import CodeCompletionDraft
from app.question_types._executable import Executable
from app.question_types._shared import (
    EXECUTABLE_CONTRACT,
    parse_tests,
    parses,
    reference_check,
    run_reference,
)
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner


class CodeCompletion(Executable):
    question_type = QuestionType.CODE_COMPLETION
    draft_model = CodeCompletionDraft
    instruction = (
        "Provide incomplete code to finish, a complete reference_solution, "
        "and executable test cases." + EXECUTABLE_CONTRACT
    )

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        reference = content.get("reference_solution")
        reference_parses = isinstance(reference, str) and parses(reference)
        tests = parse_tests(content.get("tests"))
        summary = run_reference(reference, reference_parses, tests, runner)
        return [
            make_check(
                "completion_reference_parses",
                reference_parses,
                "Reference solution parses",
            ),
            make_check("harness_valid", tests is not None, "Test harness is valid"),
            reference_check(summary, len(tests) if tests is not None else 0),
        ]


TYPE = CodeCompletion()
