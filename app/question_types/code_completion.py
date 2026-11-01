"""Code completion: finish the given code; scored by its tests (``code.python.tests``)."""

from __future__ import annotations

import ast
import re

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
        stub = content.get("code")
        incomplete = (
            isinstance(stub, str)
            and bool(_BLANK_MARKER.search(stub))
            and not (isinstance(reference, str) and _same_code(stub, reference))
        )
        return [
            make_check(
                "completion_reference_parses",
                isinstance(reference, str) and parses(reference),
                "Reference solution parses",
            ),
            make_check(
                "completion_stub_incomplete",
                incomplete,
                "Starter code leaves something to complete",
                evidence=None
                if incomplete
                else (
                    "The starter code in `code` must not be the reference solution: leave a "
                    "visible blank for the student (___, ..., pass, or a # TODO line)."
                ),
            ),
        ]


#: What marks the part the student completes. Lenient on purpose: any of these counts.
_BLANK_MARKER = re.compile(
    r"_{3,}|\.\.\.|…|\bpass\b|NotImplementedError"
    r"|#\s*(?i:todo|fixme|your code|fill|complete|write|implement|add|replace)",
)


def _same_code(stub: str, reference: str) -> bool:
    """Equal ignoring whitespace and comments (by AST when both parse, else by text)."""
    try:
        return ast.dump(ast.parse(stub)) == ast.dump(ast.parse(reference))
    except (SyntaxError, ValueError):
        return " ".join(stub.split()) == " ".join(reference.split())


TYPE = CodeCompletion()
