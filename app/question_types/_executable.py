"""What the three executable types (code completion, debugging, coding) share."""

from __future__ import annotations

from app.assessment.specs import GradingPlan, Unmarkable
from app.domain.enums import QuestionKind
from app.question_types._shared import same, stored_case_specs, tests_json
from app.question_types.base import DraftColumns, StudentView


class Executable:
    """Base for types answered with a program and scored by its tests."""

    kind = QuestionKind.TESTABLE_PROGRAM
    #: Whether the student sees the stored ``code`` (completion, debugging) or starts blank.
    shows_code = True

    def columns_from_draft(self, draft) -> DraftColumns:
        return DraftColumns(draft.prompt, draft.reference_solution, tests_json(draft.tests))

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        cases = stored_case_specs(content.get("tests")) or stored_case_specs(tests)
        if not cases:
            raise Unmarkable("no usable test cases are stored")
        # The app's own per-run limit, as the old runner used, so scores do not move.
        from app.config import get_settings

        spec: dict = {"tests": cases, "timeout_s": get_settings().validation_timeout_seconds}
        reference = content.get("reference_solution")
        if isinstance(reference, str):
            # Grading a student ignores it; ``check_spec`` runs it to prove the tests are passable.
            spec["reference_solution"] = reference
        return GradingPlan("code.python.tests", spec, same)

    def student_view(self, content: dict, *, seed: int) -> StudentView:
        del seed
        if not self.shows_code:
            return StudentView()
        code = content.get("code")
        return StudentView(code=code if isinstance(code, str) else None)
