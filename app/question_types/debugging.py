"""Debugging: fix the buggy code; scored by its tests (``code.python.tests``)."""

from __future__ import annotations

from app.domain.enums import QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import DebuggingDraft
from app.question_types._executable import Executable
from app.question_types._shared import EXECUTABLE_CONTRACT, parse_tests, parses
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner


class Debugging(Executable):
    question_type = QuestionType.DEBUGGING
    draft_model = DebuggingDraft
    instruction = (
        "Provide buggy code, ask the learner to diagnose or fix it, and provide a correct "
        "reference_solution plus executable test cases.\n"
        "The code must contain exactly one defect, and one a learner plausibly writes. "
        "reference_solution is the complete corrected program, runnable as-is -- code, never "
        "an explanation of the fix." + EXECUTABLE_CONTRACT
    )

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        """Usable tests and "the reference passes them" are ``gradable``'s (check_spec)."""
        broken = content.get("code")
        broken_parses = isinstance(broken, str) and parses(broken)
        reference = content.get("reference_solution")
        reference_parses = isinstance(reference, str) and parses(reference)
        tests = parse_tests(content.get("tests"))

        broken_exhibits_issue = not broken_parses or tests is None
        broken_evidence = None
        if broken_parses and tests is not None:
            broken_summary = runner.run_tests(broken, tests)
            broken_exhibits_issue = (
                broken_summary.passed_count < broken_summary.total
                or broken_summary.timed_out
                or any(result.exit_code not in (0, None) for result in broken_summary.results)
            )
            if broken_exhibits_issue:
                broken_evidence = broken_summary.evidence

        return [
            make_check(
                "debug_broken_exhibits_issue",
                broken_exhibits_issue,
                "Broken code exhibits the issue",
                broken_evidence,
            ),
            make_check(
                "debug_reference_parses",
                reference_parses,
                "Reference solution parses",
            ),
        ]


TYPE = Debugging()
