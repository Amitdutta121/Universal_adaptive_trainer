"""``text.normalized_match`` (C1)."""

from __future__ import annotations

import pytest

import graders
from graders import GradeResult, SpecError
from graders.text import NormalizedMatchGrader, build

GRADER = NormalizedMatchGrader()
SPEC = {"expected": "3\n4\n", "explanation": "Prints 3 then 4."}


def test_registry_returns_this_grader() -> None:
    graders.set_executor(None)
    assert isinstance(graders.get_grader("text.normalized_match"), NormalizedMatchGrader)


def test_build_satisfies_the_protocol() -> None:
    (grader,) = build(lambda: (_ for _ in ()).throw(AssertionError("executor used")))
    assert isinstance(grader, graders.Grader)
    assert grader.capability == "text.normalized_match"
    assert grader.version == "1"
    assert grader.spec_model.model_config.get("extra") == "forbid"


@pytest.mark.parametrize(
    ("answer", "score"),
    [
        ("3\n4", 1.0),
        ("3\n4\n", 1.0),
        ("3\r\n4\r\n", 1.0),
        ("3\r4\r", 1.0),
        ("3\n4\n\n", 0.0),  # only ONE trailing newline is forgiven
        ("3\n4 ", 0.0),
        (" 3\n4", 0.0),
        ("3 4", 0.0),
        ("", 0.0),
    ],
)
def test_default_normalisation(answer: str, score: float) -> None:
    assert GRADER.grade(SPEC, answer) == GradeResult(score=score, feedback="Prints 3 then 4.")


def test_two_trailing_newlines_do_not_match_one() -> None:
    assert GRADER.grade({"expected": "x\n"}, "x\n\n").score == 0.0
    assert GRADER.grade({"expected": "x\n\n"}, "x\n").score == 0.0
    assert GRADER.grade({"expected": "x\n\n"}, "x\n\n").score == 1.0
    assert GRADER.grade({"expected": "x\n\n"}, "x\r\n\r\n").score == 1.0


def test_case_is_kept_by_default_and_folded_on_request() -> None:
    assert GRADER.grade({"expected": "Hello"}, "hello").score == 0.0
    assert GRADER.grade({"expected": "Hello", "fold_case": True}, "HELLO").score == 1.0
    assert GRADER.grade({"expected": "Straße", "fold_case": True}, "STRASSE").score == 1.0


def test_whitespace_is_kept_by_default_and_collapsed_on_request() -> None:
    spec = {"expected": "a  b\tc\n", "collapse_whitespace": True}
    assert GRADER.grade({"expected": "a  b"}, "a b").score == 0.0
    assert GRADER.grade(spec, "a b c").score == 1.0
    assert GRADER.grade(spec, "  a\nb   c  \n\n").score == 1.0
    assert GRADER.grade(spec, "ab c").score == 0.0


def test_both_flags() -> None:
    spec = {"expected": "Hello  World", "fold_case": True, "collapse_whitespace": True}
    assert GRADER.grade(spec, " hello\tWORLD ").score == 1.0


def test_feedback_is_the_explanation_or_none() -> None:
    assert GRADER.grade(SPEC, "wrong").feedback == "Prints 3 then 4."
    assert GRADER.grade({"expected": "x"}, "x").feedback is None
    assert GRADER.grade({"expected": "x", "explanation": " "}, "x").feedback is None


def test_answers_never_raise_or_set_format_error() -> None:
    for answer in ["", "\x00", "\r", "\n" * 50, "é" * 1000]:
        assert GRADER.grade(SPEC, answer).format_error is None


def test_check_spec() -> None:
    assert GRADER.check_spec(SPEC) == []
    assert GRADER.check_spec({"expected": ""}) == []
    for broken in [{}, {"expected": 3}, {"expected": "x", "fold": True}, {"expected": None}]:
        assert [issue.code for issue in GRADER.check_spec(broken)] == ["invalid_spec"]


@pytest.mark.parametrize("spec", [{}, {"expected": 3}, {"expected": "x", "extra": 1}])
def test_broken_spec_raises(spec: dict) -> None:
    with pytest.raises(SpecError):
        GRADER.grade(spec, "x")


# ------------------------------------------------------------------- parity with today's scoring


@pytest.mark.parametrize(
    ("expected", "answer"),
    [
        ("3\n4\n", "3\n4"),
        ("3\n4\n", "3\r\n4\r\n"),
        ("3\n4\n", "3\n4\n\n"),
        ("3\n4", "3\n4\n"),
        ("x\n\n", "x\n"),
        ("Hello", "hello"),
        ("a  b", "a b"),
        ("", "\n"),
        ("", ""),
    ],
)
def test_parity_output_prediction(expected: str, answer: str) -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from grading_oracle import score_answer

    from app.domain.enums import QuestionType
    from app.domain.questions import Question

    question = Question(
        question_type=QuestionType.OUTPUT_PREDICTION,
        prompt="q",
        content={"expected_output": expected},
    )
    app_score = score_answer(question, answer).score
    assert GRADER.grade({"expected": expected}, answer).score * 100 == app_score
