"""Code completion: finish the given code; scored by its tests (``code.python.tests``)."""

from __future__ import annotations

from app.domain.enums import QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import CodeCompletionDraft
from app.question_types._executable import Executable
from app.question_types._shared import EXECUTABLE_CONTRACT, parses
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
        """Usable tests and "the reference passes them" are ``gradable``'s (check_spec).

        A reference is still required here: grading a student does not need one, so
        ``check_spec`` cannot tell a missing reference from a question that has none.
        """
        del runner
        reference = content.get("reference_solution")
        return [
            make_check(
                "completion_reference_parses",
                isinstance(reference, str) and parses(reference),
                "Reference solution parses",
            ),
        ]


TYPE = CodeCompletion()
