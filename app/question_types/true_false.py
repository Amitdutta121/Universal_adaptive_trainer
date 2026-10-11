"""True / false: graded by ``structured.choice`` over the two options ``true`` and ``false``."""

from __future__ import annotations

from app.assessment.specs import GradingPlan, Unmarkable
from app.domain.enums import QuestionKind, QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import TrueFalseDraft
from app.question_types._shared import explanation, present_text
from app.question_types.base import DraftColumns, StudentView
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner


def _true_false_answer(answer: str) -> str:
    submitted = answer.strip().casefold() if isinstance(answer, str) else ""
    return {"true": "0", "false": "1"}.get(submitted, "not an option")


class TrueFalse:
    question_type = QuestionType.TRUE_FALSE
    kind = QuestionKind.DISCRETE
    draft_model = TrueFalseDraft
    instruction = (
        "Write one true-or-false statement that is definitely true or definitely false as "
        "written, with no exception a careful reader could raise. "
        "Set correct_answer to its truth value."
    )

    def columns_from_draft(self, draft: TrueFalseDraft) -> DraftColumns:
        return DraftColumns(draft.prompt, "true" if draft.correct_answer else "false", None)

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        del tests
        expected = content.get("correct_answer")
        if not isinstance(expected, bool):
            raise Unmarkable("no correct answer is recorded")
        return GradingPlan(
            "structured.choice",
            {
                "options": ["true", "false"],
                "correct": [0 if expected else 1],
                "explanation": explanation(content),
            },
            _true_false_answer,
        )

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        """A boolean ``correct_answer`` is ``gradable``'s (the grading plan requires one)."""
        del runner
        return [
            make_check(
                "tf_explanation_present",
                present_text(content.get("explanation")),
                "Explanation exists",
            ),
        ]

    def student_view(self, content: dict, *, seed: int) -> StudentView:
        del content, seed
        return StudentView()


TYPE = TrueFalse()
