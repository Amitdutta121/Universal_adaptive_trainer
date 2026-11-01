"""Output prediction: what does this code print? Graded by ``text.normalized_match``."""

from __future__ import annotations

from app.assessment.specs import GradingPlan, Unmarkable
from app.domain.enums import QuestionKind, QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import OutputPredictionDraft
from app.question_types._shared import explanation, parses, same, script_evidence
from app.question_types.base import DraftColumns, StudentView
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner, normalize_output


def observed_expected_output(code: str, runner: LocalCodeRunner | None = None) -> str | None:
    """The output a real run of ``code`` prints, or ``None`` when the code does not run.

    A question that asks "what does this print?" is answered by the run, not by the
    text the model wrote in ``expected_output``. A snippet that does not parse, does
    not exit cleanly, or times out has no output to use, and the answer check still
    fails it.
    """
    if not parses(code):
        return None
    result = (runner or LocalCodeRunner()).run_script(code)
    if result.timed_out or result.exit_code != 0:
        return None
    return normalize_output(result.stdout)


class OutputPrediction:
    question_type = QuestionType.OUTPUT_PREDICTION
    kind = QuestionKind.DISCRETE
    draft_model = OutputPredictionDraft
    instruction = (
        "Provide a short runnable code snippet and ask for its exact output. "
        "The stored answer is the output of a real run of that code. "
        "Write code that runs to completion and prints the output the question asks about."
    )

    def columns_from_draft(self, draft: OutputPredictionDraft) -> DraftColumns:
        return DraftColumns(draft.prompt, draft.expected_output, None)

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        del tests
        expected = content.get("expected_output")
        if not isinstance(expected, str):
            raise Unmarkable("no expected output is recorded")
        return GradingPlan(
            "text.normalized_match",
            {"expected": expected, "explanation": explanation(content)},
            same,
        )

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        source = content.get("code")
        code_parses = isinstance(source, str) and parses(source)
        expected = content.get("expected_output")
        output_verified = False
        evidence = None
        if code_parses and isinstance(expected, str):
            result = runner.run_script(source)
            output_verified = (
                not result.timed_out
                and result.exit_code == 0
                and normalize_output(result.stdout) == normalize_output(expected)
            )
            if not output_verified:
                evidence = script_evidence(result, expected)
        return [
            make_check("output_code_parses", code_parses, "Prediction code parses"),
            make_check(
                "expected_output_verified",
                output_verified,
                "Expected output verified",
                evidence,
            ),
        ]

    def student_view(self, content: dict, *, seed: int) -> StudentView:
        del seed
        code = content.get("code")
        return StudentView(code=code if isinstance(code, str) else None)


TYPE = OutputPrediction()
