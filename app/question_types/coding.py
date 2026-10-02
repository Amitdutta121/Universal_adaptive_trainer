"""Coding: write a small implementation from scratch; scored by its tests."""

from __future__ import annotations

from app.domain.enums import QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import CodingDraft
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
        reference = content.get("reference_solution")
        reference_parses = isinstance(reference, str) and parses(reference)
        tests = parse_tests(content.get("tests"))
        summary = run_reference(reference, reference_parses, tests, runner)
        return [
            make_check(
                "coding_reference_parses",
                reference_parses,
                "Reference solution parses",
            ),
            make_check("harness_valid", tests is not None, "Test harness is valid"),
            reference_check(summary, len(tests) if tests is not None else 0),
        ]


TYPE = Coding()
