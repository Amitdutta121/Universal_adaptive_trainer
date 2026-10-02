"""Equation response: the student writes an expression or an equation (phase 2, T2).

Graded by ``symbolic.expression_equivalence`` (``graders/symbolic.py``): any answer equivalent to
``expected`` earns full marks, so the question asks for a quantity, never for a particular form.
The answer convention is the grader's: ``^`` or ``**`` for powers, implicit multiplication
(``2x``), and ``lhs = rhs`` in equation mode, where a nonzero multiple of the expected equation
also counts (``2y = 4x`` matches ``y = 2x``).

Whether ``expected`` parses, uses only declared variables and is checkable numerically is the
grader's ``check_spec``, which the generic ``gradable`` check (C8) runs for every type; the checks
here are only the ones that are not about grading.
"""

from __future__ import annotations

import re

from pydantic import Field, model_validator

from app.assessment.specs import GradingPlan, Unmarkable
from app.domain.enums import QuestionKind, QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import TaxonomyClaim
from app.question_types._shared import explanation, present_text, same
from app.question_types.base import DraftColumns, StudentView
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner

#: A variable name the grader accepts: a letter, then letters, digits or single underscores.
_VARIABLE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
#: Characters that make an expected answer more than a lone symbol or number.
_OPERATORS = frozenset("+-*/^()=")


class EquationResponseDraft(TaxonomyClaim):
    """Equation-response question draft."""

    prompt: str = Field(min_length=1)
    expected: str = Field(
        min_length=1,
        description=(
            "One correct answer in plain math syntax, e.g. 'm*g*h' or, in equation mode, "
            "'v = v_0 + a*t'."
        ),
    )
    variables: list[str] = Field(
        description="Every symbol the answer uses, e.g. ['m', 'g', 'h']. Empty for a number."
    )
    equation: bool = Field(
        default=False,
        description="True when the answer is a relation written as left = right.",
    )
    allowed_functions: list[str] | None = Field(
        default=None,
        description="Restricts which functions an answer may use. Leave unset to allow all.",
    )
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _answer_shape_is_consistent(self) -> EquationResponseDraft:
        invalid = [name for name in self.variables if not _VARIABLE.fullmatch(name) or "__" in name]
        if invalid:
            raise ValueError(f"variables must be plain names such as x or v_0, not {invalid}.")
        if len(set(self.variables)) != len(self.variables):
            raise ValueError("variables must not list a name twice.")
        signs = self.expected.count("=")
        if self.equation and signs != 1:
            raise ValueError("In equation mode, expected must contain exactly one '='.")
        if not self.equation and signs:
            raise ValueError("expected contains '='; set equation to true or give an expression.")
        if self.allowed_functions is not None:
            from graders.symbolic import SAFE_NAMES

            unknown = [name for name in self.allowed_functions if name not in SAFE_NAMES]
            if unknown:
                raise ValueError(
                    f"allowed_functions may only name {sorted(SAFE_NAMES)}, not {unknown}."
                )
        return self


def _compact(text: str) -> str:
    return "".join(text.split())


def _names(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return value


class EquationResponse:
    question_type = QuestionType.EQUATION_RESPONSE
    kind = QuestionKind.DISCRETE
    draft_model = EquationResponseDraft
    instruction = (
        "Ask for one expression or equation the student writes from what the section "
        "teaches, such as a formula, a derived quantity or a rearranged relation. "
        "Set expected to one correct answer in plain math syntax: * for multiplication, "
        "^ for powers, parentheses for grouping, and only the functions sin, cos, tan, "
        "asin, acos, atan, sinh, cosh, tanh, exp, log, ln, sqrt and abs, with the "
        "constants pi and E. "
        "Declare every symbol the answer uses in variables, as plain names such as x, v_0 "
        "or theta, and name each of them in the prompt so the student knows which symbols "
        "to write. "
        "Any answer equivalent to expected earns full marks, so ask for a quantity, not "
        "for a particular form such as expanded or factored. "
        "Set equation to true only when the answer is a relation written as left = right, "
        "with exactly one =; otherwise expected contains no =. "
        "Never state the answer in the prompt. Explain in explanation how it is obtained."
    )

    def columns_from_draft(self, draft: EquationResponseDraft) -> DraftColumns:
        return DraftColumns(draft.prompt, draft.expected, None)

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        del tests
        expected = content.get("expected")
        if not isinstance(expected, str) or not expected.strip():
            raise Unmarkable("no expected expression is recorded")
        variables = _string_list(content.get("variables", []))
        if variables is None:
            raise Unmarkable("the variables are not a list of names")
        spec: dict[str, object] = {
            "expected": expected,
            "variables": variables,
            "equation": content.get("equation") is True,
            "explanation": explanation(content),
        }
        allowed = content.get("allowed_functions")
        if allowed is not None:
            functions = _string_list(allowed)
            if functions is None:
                raise Unmarkable("the allowed functions are not a list of names")
            spec["allowed_functions"] = functions
        return GradingPlan("symbolic.expression_equivalence", spec, same)

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        del runner
        expected = content.get("expected")
        prompt = content.get("prompt")
        compact_expected = _compact(expected) if isinstance(expected, str) else ""
        # A lone symbol ("v") is bound to appear in its own question, so only an answer with an
        # operator in it can be said to be given away.
        leaked = (
            bool(compact_expected)
            and bool(_OPERATORS & set(compact_expected))
            and isinstance(prompt, str)
            and compact_expected in _compact(prompt)
        )
        return [
            make_check(
                "equation_explanation_present",
                present_text(content.get("explanation")),
                "Explanation exists",
            ),
            make_check(
                "equation_answer_not_in_prompt",
                not leaked,
                "Prompt does not state the answer",
                f"The prompt contains the expected answer {expected!r}." if leaked else None,
            ),
        ]

    def student_view(self, content: dict, *, seed: int) -> StudentView:
        del seed
        variables = _string_list(content.get("variables")) or []
        what = "an equation, left = right," if content.get("equation") is True else "an expression"
        using = f" using {_names(variables)}" if variables else ""
        parts = [
            f"Write {what}{using}.",
            "Use ^ for powers (x^2) and * for multiplication; 2x also means 2*x.",
        ]
        allowed = _string_list(content.get("allowed_functions"))
        if allowed is not None:
            names = [name for name in allowed if name not in ("pi", "E")]
            parts.append(
                f"Functions you may use: {', '.join(names)}." if names else "Use no functions."
            )
        return StudentView(answer_hint=" ".join(parts))


TYPE = EquationResponse()
