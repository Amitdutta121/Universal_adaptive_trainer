"""The generic ``gradable`` check: grading plan + the grader's ``check_spec`` (C8)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import app.question_types as question_types
from app.assessment.specs import GradingPlan, Unmarkable
from app.domain.enums import QuestionKind, QuestionType
from app.domain.questions import Question, QuestionCheck
from app.errors import CodeExecutionUnavailableError
from app.validation import DeterministicQuestionValidator
from app.validation.gradable import check_gradable
from app.validation.runner import EVIDENCE_LIMIT
from graders import set_executor
from graders.executors import RunRequest, RunResult

ADD = "def add(a, b):\n    return a + b"
ADD_TEST = [{"assert": "assert add(1, 2) == 3"}]

#: One passing stored question per built type.
VALID: dict[QuestionType, dict[str, object]] = {
    QuestionType.MULTIPLE_CHOICE: {
        "options": ["one", "two"],
        "correct_option_index": 1,
        "explanation": "Why.",
    },
    QuestionType.TRUE_FALSE: {"correct_answer": False, "explanation": "Why."},
    QuestionType.OUTPUT_PREDICTION: {"code": "print(3)", "expected_output": "3"},
    QuestionType.CODE_COMPLETION: {
        "code": "def add(a, b): ...",
        "reference_solution": ADD,
        "tests": ADD_TEST,
    },
    QuestionType.DEBUGGING: {
        "code": "def add(a, b):\n    return a - b",
        "reference_solution": ADD,
        "tests": ADD_TEST,
    },
    QuestionType.PARSONS: {
        "blocks": [
            {"id": "a", "text": "if True:", "indent": 0},
            {"id": "b", "text": "print(1)", "indent": 1},
        ],
        "correct_order": ["a", "b"],
    },
    QuestionType.CODING: {"reference_solution": ADD, "tests": ADD_TEST},
}


@pytest.fixture(autouse=True)
def _reset_executor():
    yield
    set_executor(None)


def _question(question_type: QuestionType | None, content: dict[str, object]) -> Question:
    return Question(
        id=1, prompt="Validate this question.", question_type=question_type, content=content
    )


def _report_checks(
    question_type: QuestionType, content: dict[str, object]
) -> dict[str, QuestionCheck]:
    report = DeterministicQuestionValidator().validate(_question(question_type, content))
    return {check.name: check for check in report.checks}


def _gradable(question_type: QuestionType, content: dict[str, object]) -> QuestionCheck:
    return _report_checks(question_type, content)["gradable"]


@pytest.mark.parametrize("question_type", list(VALID))
def test_a_valid_question_of_every_built_type_is_gradable(question_type: QuestionType) -> None:
    check = _gradable(question_type, VALID[question_type])

    assert check.passed is True
    assert check.evidence is None


def test_every_implemented_type_is_covered() -> None:
    # A type added later is checked too; this only keeps the fixtures above honest.
    assert set(question_types.implemented_types()) >= set(VALID)


@pytest.mark.parametrize(
    ("question_type", "content", "evidence"),
    [
        (
            QuestionType.MULTIPLE_CHOICE,
            {"options": ["one", "two"], "correct_option_index": 9, "explanation": "Why."},
            "the correct option is not among the options",
        ),
        (
            QuestionType.MULTIPLE_CHOICE,
            {"options": ["one"], "correct_option_index": 0, "explanation": "Why."},
            "too_few_options",
        ),
        (
            QuestionType.MULTIPLE_CHOICE,
            {"options": ["one", " "], "correct_option_index": 0, "explanation": "Why."},
            "empty_option",
        ),
        (
            QuestionType.TRUE_FALSE,
            {"correct_answer": "yes", "explanation": "Why."},
            "no correct answer is recorded",
        ),
        (
            QuestionType.OUTPUT_PREDICTION,
            {"code": "print(3)"},
            "no expected output is recorded",
        ),
        (
            QuestionType.CODE_COMPLETION,
            {"reference_solution": "print(1)", "tests": [{}]},
            "no usable test cases are stored",
        ),
        (
            QuestionType.CODE_COMPLETION,
            {"reference_solution": "def add(a, b):\n    return a * b", "tests": ADD_TEST},
            "reference_fails_tests: The reference solution passes 0 of 1 tests.",
        ),
        (
            QuestionType.DEBUGGING,
            {"code": "print(2)", "reference_solution": "print(1)", "tests": [{"stdout": "2"}]},
            "reference_fails_tests",
        ),
        (
            QuestionType.CODING,
            {"reference_solution": "print(1)", "tests": [{"stdout": "2"}]},
            "reference_fails_tests",
        ),
        (
            QuestionType.PARSONS,
            {
                "blocks": [{"id": "a", "text": "print(3)", "indent": 0}],
                "correct_order": ["a", "ghost"],
            },
            "block 'ghost' has no valid indentation recorded",
        ),
        (
            QuestionType.PARSONS,
            {
                "blocks": [{"id": "a", "text": "print(3)", "indent": -1}],
                "correct_order": ["a"],
            },
            "no valid indentation",
        ),
        (
            QuestionType.PARSONS,
            {
                "blocks": [{"id": "a", "text": "print(3)", "indent": 0}],
                "correct_order": ["a", "a"],
            },
            "duplicate_block",
        ),
    ],
)
def test_an_ungradable_question_fails_with_the_reason(
    question_type: QuestionType, content: dict[str, object], evidence: str
) -> None:
    check = _gradable(question_type, content)

    assert check.passed is False
    assert evidence in (check.evidence or "")


def test_ungradable_questions_fail_the_whole_report() -> None:
    # The three named in the C8 acceptance: out-of-range option, failing reference, unknown block.
    cases = [
        (
            QuestionType.MULTIPLE_CHOICE,
            {"options": ["a", "b"], "correct_option_index": 2, "explanation": "Why."},
        ),
        (QuestionType.CODING, {"reference_solution": "print(1)", "tests": [{"stdout": "2"}]}),
        (
            QuestionType.PARSONS,
            {
                "blocks": [{"id": "a", "text": "x = 1", "indent": 0}],
                "correct_order": ["a", "ghost"],
            },
        ),
    ]
    for question_type, content in cases:
        report = DeterministicQuestionValidator().validate(_question(question_type, content))
        assert report.passed is False
        assert {check.name for check in report.checks if not check.passed} >= {"gradable"}


def test_the_tests_column_is_used_when_content_has_none() -> None:
    # As scoring does (plan_for falls back to the column): gradable = scoring can mark it.
    question = Question(
        id=1,
        prompt="p",
        question_type=QuestionType.CODING,
        content={"reference_solution": ADD},
        tests='[{"assert": "assert add(1, 2) == 3"}]',
    )

    [check] = check_gradable(question, question.content or {})

    assert check.passed is True


def test_a_missing_reference_is_not_run_but_still_fails_the_type_check() -> None:
    checks = _report_checks(QuestionType.CODING, {"tests": ADD_TEST})

    assert checks["gradable"].passed is True  # gradable for students: tests are usable
    assert checks["coding_reference_parses"].passed is False


def test_evidence_is_bounded() -> None:
    long_name = "x" * (EVIDENCE_LIMIT * 2)
    content = {"reference_solution": "print(1)", "tests": [{"stdout": long_name}]}

    evidence = _gradable(QuestionType.CODING, content).evidence

    assert evidence is not None
    assert len(evidence) <= EVIDENCE_LIMIT


class _DownExecutor:
    def run(self, request: RunRequest) -> RunResult:
        del request
        return RunResult("", "sandbox down", None, False, "down")


def test_an_executor_outage_propagates_instead_of_failing_the_check() -> None:
    set_executor(_DownExecutor)
    question = _question(QuestionType.CODING, VALID[QuestionType.CODING])

    with pytest.raises(CodeExecutionUnavailableError):
        check_gradable(question, VALID[QuestionType.CODING])


# --- registry-only: a type added later, and a type that is not built ---------------------------


@dataclass
class _LaterType:
    """Stands in for a type module that lands after C8 (e.g. numeric_response)."""

    plan: GradingPlan | None
    question_type: QuestionType = QuestionType.NUMERIC_RESPONSE
    kind: QuestionKind = QuestionKind.DISCRETE

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        del content, tests
        if self.plan is None:
            raise Unmarkable("no value is recorded")
        return self.plan

    def authoring_checks(self, content: dict, runner: object) -> list[QuestionCheck]:
        del content, runner
        return []


def _register(monkeypatch: pytest.MonkeyPatch, module: object | None) -> None:
    real = question_types.get_type

    def get_type(question_type: QuestionType):
        if question_type is QuestionType.NUMERIC_RESPONSE:
            if module is None:
                raise KeyError(question_type)
            return module
        return real(question_type)

    monkeypatch.setattr(question_types, "get_type", get_type)


def _choice_plan(correct: int) -> GradingPlan:
    return GradingPlan("structured.choice", {"options": ["a", "b"], "correct": [correct]}, str)


@pytest.mark.parametrize(
    ("plan", "passed", "evidence"),
    [
        (_choice_plan(0), True, None),
        (_choice_plan(5), False, "correct_out_of_range"),
        (None, False, "no value is recorded"),
        (GradingPlan("not.a.capability", {}, str), False, "No grader is built"),
        (GradingPlan("structured.choice", {"options": "nope"}, str), False, "invalid_spec"),
    ],
)
def test_a_type_added_later_is_checked_through_the_registries(
    monkeypatch: pytest.MonkeyPatch, plan: GradingPlan | None, passed: bool, evidence: str | None
) -> None:
    _register(monkeypatch, _LaterType(plan))

    check = _gradable(QuestionType.NUMERIC_RESPONSE, {})

    assert check.passed is passed
    if evidence is None:
        assert check.evidence is None
    else:
        assert evidence in (check.evidence or "")


def test_an_unbuilt_type_fails_question_type_built_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _register(monkeypatch, None)

    checks = _report_checks(QuestionType.NUMERIC_RESPONSE, {"value": 1})

    assert checks["question_type_built"].passed is False
    assert "gradable" not in checks


def test_no_question_type_has_no_gradable_check() -> None:
    assert check_gradable(_question(None, {}), {}) == []
