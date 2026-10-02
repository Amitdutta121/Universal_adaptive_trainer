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


class OutputPrediction:
    question_type = QuestionType.OUTPUT_PREDICTION
    kind = QuestionKind.DISCRETE
    draft_model = OutputPredictionDraft
    instruction = (
        "Provide a short runnable code snippet and ask for its exact output. "
        "Set expected_output exactly, including line breaks."
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
