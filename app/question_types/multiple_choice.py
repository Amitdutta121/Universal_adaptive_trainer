"""Multiple choice: pick one option; graded by ``structured.choice``."""

from __future__ import annotations

from app.assessment.specs import GradingPlan, Unmarkable
from app.domain.enums import QuestionKind, QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import MultipleChoiceDraft
from app.question_types._shared import explanation, present_text, same
from app.question_types.base import DraftColumns, StudentView
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner


class MultipleChoice:
    question_type = QuestionType.MULTIPLE_CHOICE
    kind = QuestionKind.DISCRETE
    draft_model = MultipleChoiceDraft
    instruction = (
        "Write a multiple-choice question with plausible alternatives. "
        "Set correct_option_index to the zero-based index of the one correct option."
    )

    def columns_from_draft(self, draft: MultipleChoiceDraft) -> DraftColumns:
        return DraftColumns(draft.prompt, draft.options[draft.correct_option_index], None)

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        del tests
        index = content.get("correct_option_index")
        options = content.get("options")
        if not isinstance(index, int) or isinstance(index, bool):
            raise Unmarkable("no correct option is recorded")
        if not isinstance(options, list) or index >= len(options) or index < 0:
            raise Unmarkable("the correct option is not among the options")
        return GradingPlan(
            "structured.choice",
            {
                "options": [str(option) for option in options],
                "correct": [index],
                "explanation": explanation(content),
            },
            same,
        )

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        del runner
        options = content.get("options")
        options_valid = (
            isinstance(options, list)
            and len(options) >= 2
            and all(isinstance(option, str) and bool(option.strip()) for option in options)
        )
        no_duplicates = options_valid and len(set(options)) == len(options)
        correct_index = content.get("correct_option_index")
        correct_exists = (
            options_valid
            and isinstance(correct_index, int)
            and not isinstance(correct_index, bool)
            and 0 <= correct_index < len(options)
        )
        explanation_present = present_text(content.get("explanation"))
        return [
            make_check("mc_options_valid", options_valid, "Options are valid"),
            make_check("mc_no_duplicate_options", no_duplicates, "No duplicate options"),
            make_check(
                "mc_correct_option_exists",
                correct_exists,
                "Correct-answer reference exists",
            ),
            make_check(
                "mc_explanation_present",
                explanation_present,
                "Explanation exists",
            ),
        ]

    def student_view(self, content: dict, *, seed: int) -> StudentView:
        del seed
        options = content.get("options")
        if not isinstance(options, list):
            return StudentView()
        return StudentView(options=[str(option) for option in options])


TYPE = MultipleChoice()
