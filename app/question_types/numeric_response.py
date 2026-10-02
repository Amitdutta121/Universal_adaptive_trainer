"""Numeric response: one number with its unit, graded by ``quantity.units``.

The draft is stored whole as ``content``; the grader spec is read from it. The student answers
with one string, number first and unit after (``"9.81 m/s^2"``), which is exactly the grader's
answer convention, so the answer is passed through unchanged. Unit parsing, conversion and the
"is this spec gradable at all" question belong to the grader (and to the generic ``gradable``
check, C8); this module only checks what is not about grading.
"""

from __future__ import annotations

import math
import re
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.assessment.specs import GradingPlan, Unmarkable
from app.domain.enums import QuestionKind, QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import TaxonomyClaim
from app.question_types._shared import explanation, present_text, same
from app.question_types.base import DraftColumns, StudentView
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner

#: Unit strings that mean "a pure number"; the grader then accepts a bare number.
_DIMENSIONLESS = frozenset({"", "1", "dimensionless"})

#: Decimal numbers as a prompt would write them: 9.81, -3, .5, 1.2e3, 6.02 x 10^23 is not
#: recognised (it reads as 6.02 and 10 and 23), which only makes the give-away check lenient.
_PROMPT_NUMBER = re.compile(r"(?<![\w.])[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


class NumericResponseDraft(TaxonomyClaim):
    """Numeric-response question draft: the answer is one number with a unit."""

    prompt: str = Field(min_length=1)
    value: float = Field(
        allow_inf_nan=False,
        description="The correct answer's number, expressed in `unit`.",
    )
    unit: str = Field(
        description=(
            'The correct answer\'s unit as a standard symbol, e.g. "m/s^2", "kJ", "mol/L". '
            'Use "" when the answer is a pure number (a count, a ratio).'
        ),
    )
    relative_tolerance: float | None = Field(
        default=0.01,
        ge=0,
        allow_inf_nan=False,
        description="How close an answer must be, as a fraction of value (0.01 means 1%).",
    )
    absolute_tolerance: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="How close an answer must be, in `unit`. Required when value is 0.",
    )
    accepted_units: list[str] | None = Field(
        default=None,
        description=(
            "Only when the answer must be given in particular units: those units, including "
            "`unit` itself. Leave unset to accept any unit of the same quantity."
        ),
    )
    sig_figs: int | None = Field(
        default=None,
        ge=1,
        description="Only when significant figures are assessed: the minimum the answer needs.",
    )
    explanation: str = Field(min_length=1)

    @field_validator("unit")
    @classmethod
    def _strip_unit(cls, unit: str) -> str:
        return unit.strip()

    @field_validator("accepted_units")
    @classmethod
    def _accepted_units_are_named(cls, units: list[str] | None) -> list[str] | None:
        if units is None:
            return None
        cleaned = [unit.strip() for unit in units]
        if not cleaned or not all(cleaned):
            raise ValueError("accepted_units, when given, must name at least one unit.")
        return cleaned

    @model_validator(mode="after")
    def _some_tolerance_is_usable(self) -> NumericResponseDraft:
        relative = self.relative_tolerance or 0.0
        absolute = self.absolute_tolerance or 0.0
        if self.value == 0 and absolute <= 0:
            raise ValueError("value is 0, so give an absolute_tolerance above 0.")
        if relative <= 0 and absolute <= 0:
            raise ValueError("give a relative_tolerance or an absolute_tolerance above 0.")
        return self


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _is_dimensionless(unit: str) -> bool:
    return unit.strip().casefold() in _DIMENSIONLESS


def _format_number(value: float) -> str:
    """Shortest exact text for a stored value: 9.81, 20, 6.02e+23."""
    return f"{int(value)}" if value.is_integer() and abs(value) < 1e15 else repr(value)


def _states_value(prompt: str, value: float) -> bool:
    """Whether the prompt writes the answer's number itself (the same number, not a near one)."""
    for match in _PROMPT_NUMBER.finditer(prompt):
        try:
            number = float(match.group())
        except ValueError:
            continue
        if math.isclose(number, value, rel_tol=1e-9, abs_tol=0.0):
            return True
    return False


class NumericResponse:
    question_type = QuestionType.NUMERIC_RESPONSE
    kind = QuestionKind.DISCRETE
    draft_model = NumericResponseDraft
    instruction = (
        "Write a question whose answer is a single number with a unit, worked out from the "
        "given quantities rather than read off the text. Set value to the correct answer and "
        'unit to its unit as a standard symbol (e.g. m/s^2, kJ, mol/L; "" for a pure number). '
        "Set relative_tolerance (a fraction, 0.01 for 1%) and/or absolute_tolerance (in unit) "
        "to how close an answer must be to count as correct. Set accepted_units only if the "
        "answer must be given in particular units, and sig_figs only if significant figures "
        "are part of what is assessed. Never state the answer's value in the prompt."
    )

    def columns_from_draft(self, draft: NumericResponseDraft) -> DraftColumns:
        reference = f"{_format_number(draft.value)} {draft.unit}".strip()
        return DraftColumns(draft.prompt, reference, None)

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        del tests
        value = _number(content.get("value"))
        if value is None:
            raise Unmarkable("no numeric value is recorded")
        unit = content.get("unit")
        if not isinstance(unit, str):
            raise Unmarkable("no unit is recorded")
        relative = _number(content.get("relative_tolerance"))
        absolute = _number(content.get("absolute_tolerance"))
        spec: dict[str, Any] = {
            "value": value,
            "unit": unit,
            "tolerance": (
                None
                if relative is None and absolute is None
                else {"relative": relative, "absolute": absolute}
            ),
            "accepted_units": content.get("accepted_units"),
            "sig_figs": content.get("sig_figs"),
            "explanation": explanation(content),
        }
        return GradingPlan("quantity.units", spec, same)

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        del runner
        value = _number(content.get("value"))
        prompt = content.get("prompt")
        gives_away = value is not None and isinstance(prompt, str) and _states_value(prompt, value)
        return [
            make_check(
                "numeric_value_not_in_prompt",
                value is not None and not gives_away,
                "The prompt does not state the answer",
                f"The prompt contains the answer's number {_format_number(value)}."
                if gives_away and value is not None
                else None,
            ),
            make_check(
                "numeric_explanation_present",
                present_text(content.get("explanation")),
                "Explanation exists",
            ),
        ]

    def student_view(self, content: dict, *, seed: int) -> StudentView:
        del seed
        unit = content.get("unit")
        unit = unit.strip() if isinstance(unit, str) else ""
        accepted = content.get("accepted_units")
        if isinstance(accepted, list) and accepted and all(isinstance(u, str) for u in accepted):
            hint = f"Give a number with its unit, in {' or '.join(accepted)}."
        elif _is_dimensionless(unit):
            hint = "Give a number."
        else:
            hint = f"Give a number with its unit, e.g. in {unit}."
        sig_figs = content.get("sig_figs")
        if isinstance(sig_figs, int) and not isinstance(sig_figs, bool) and sig_figs > 0:
            hint += f" Use at least {sig_figs} significant figures."
        return StudentView(answer_hint=hint)


TYPE = NumericResponse()
