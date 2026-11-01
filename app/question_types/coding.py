"""Coding: write a small implementation from scratch; scored by its tests."""

from __future__ import annotations

from app.domain.enums import QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import CodingDraft
from app.question_types._executable import Executable
from app.question_types._shared import EXECUTABLE_CONTRACT, parses
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner


class Coding(Executable):
    question_type = QuestionType.CODING
    draft_model = CodingDraft
    shows_code = False
    instruction = (
        "Ask for a small implementation, then provide a complete reference_solution and "
        "executable test cases. Name the function, its parameters and what it returns, so "
        "one correct implementation is obvious in shape." + EXECUTABLE_CONTRACT
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
                "coding_reference_parses",
                isinstance(reference, str) and parses(reference),
                "Reference solution parses",
            ),
        ]


TYPE = Coding()
