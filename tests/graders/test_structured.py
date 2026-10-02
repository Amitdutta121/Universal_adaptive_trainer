"""``structured.choice`` and ``structured.ordering`` (C1)."""

from __future__ import annotations

import pytest

import graders
from graders import GradeResult, SpecError
from graders.structured import ChoiceGrader, OrderingGrader, build

CHOICE = ChoiceGrader()
ORDERING = OrderingGrader()

MC = {"options": ["a", "b", "c", "d"], "correct": [2], "explanation": "Because c."}
MULTI = {"options": ["a", "b", "c", "d"], "correct": [0, 2], "explanation": "a and c."}
TF = {"options": ["True", "False"], "correct": [1], "answer_by": "text", "explanation": "No."}
PARSONS = {
    "blocks": [
        {"id": "def", "indent": 0},
        {"id": "loop", "indent": 1},
        {"id": "body", "indent": 2},
        {"id": "ret", "indent": 1},
    ],
    "correct_order": ["def", "loop", "body", "ret"],
    "explanation": "Return after the loop.",
}
FLAT = {
    "blocks": [{"id": "a", "indent": 0}, {"id": "b", "indent": 0}, {"id": "c", "indent": 0}],
    "correct_order": ["a", "b", "c"],
}


def codes(issues) -> set[str]:
    return {issue.code for issue in issues}


# ------------------------------------------------------------------------------------- registry


def test_registry_returns_these_graders() -> None:
    graders.set_executor(None)
    assert isinstance(graders.get_grader("structured.choice"), ChoiceGrader)
    assert isinstance(graders.get_grader("structured.ordering"), OrderingGrader)
    assert {"structured.choice", "structured.ordering"} <= set(graders.available_capabilities())


def test_build_ignores_the_executor_and_satisfies_the_protocol() -> None:
    built = build(lambda: (_ for _ in ()).throw(AssertionError("executor used")))
    assert [g.capability for g in built] == ["structured.choice", "structured.ordering"]
    for grader in built:
        assert isinstance(grader, graders.Grader)
        assert grader.version == "1"
        assert grader.spec_model.model_config.get("extra") == "forbid"


# ------------------------------------------------------------------------------ choice: grading


@pytest.mark.parametrize(
    ("answer", "score"),
    [("2", 1.0), (" 2\n", 1.0), ("+2", 1.0), ("1", 0.0), ("9", 0.0), ("-1", 0.0)],
)
def test_single_correct_index(answer: str, score: float) -> None:
    result = CHOICE.grade(MC, answer)
    assert result == GradeResult(score=score, feedback="Because c.")


@pytest.mark.parametrize("answer", ["", "c", "two", "2.0", "0,2"])
def test_single_correct_unreadable_is_wrong_not_an_error(answer: str) -> None:
    result = CHOICE.grade(MC, answer)
    assert result.score == 0.0
    assert result.format_error
    assert result.feedback == "Because c."


@pytest.mark.parametrize(
    ("answer", "score"),
    [
        ("0,2", 1.0),
        ("2, 0", 1.0),
        ("0 2", 1.0),
        ("0\n2", 1.0),
        ("0,2,2", 1.0),
        ("0", 0.0),
        ("0,1,2", 0.0),
        ("0,7", 0.0),
    ],
)
def test_multi_correct_is_set_equality(answer: str, score: float) -> None:
    result = CHOICE.grade(MULTI, answer)
    assert result.score == score
    assert result.format_error is None
    assert result.feedback == "a and c."


@pytest.mark.parametrize("answer", ["", " , ", "0,b", "a c"])
def test_multi_correct_unreadable(answer: str) -> None:
    result = CHOICE.grade(MULTI, answer)
    assert result.score == 0.0
    assert result.format_error
    assert result.feedback == "a and c."


@pytest.mark.parametrize(
    ("answer", "score", "unreadable"),
    [
        ("false", 1.0, False),
        ("  FALSE ", 1.0, False),
        ("true", 0.0, False),
        ("1", 0.0, True),
        ("maybe", 0.0, True),
    ],
)
def test_text_answers(answer: str, score: float, unreadable: bool) -> None:
    result = CHOICE.grade(TF, answer)
    assert result.score == score
    assert bool(result.format_error) is unreadable
    assert result.feedback == "No."


def test_blank_explanation_gives_no_feedback() -> None:
    assert CHOICE.grade({**MC, "explanation": "  "}, "2").feedback is None
    assert CHOICE.grade({"options": ["a", "b"], "correct": [0]}, "0").feedback is None


# ---------------------------------------------------------------------------- choice: the spec


def test_good_choice_specs_have_no_issues() -> None:
    assert CHOICE.check_spec(MC) == []
    assert CHOICE.check_spec(MULTI) == []
    assert CHOICE.check_spec(TF) == []


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        ({"options": ["a", "b"], "correct": [2]}, "correct_out_of_range"),
        ({"options": ["a", "b"], "correct": [-1]}, "correct_out_of_range"),
        ({"options": ["a", "b"], "correct": [0, 0]}, "duplicate_correct"),
        ({"options": ["a", "b"], "correct": []}, "no_correct_option"),
        ({"options": ["a"], "correct": [0]}, "too_few_options"),
        ({"options": ["a", " "], "correct": [0]}, "empty_option"),
        ({**TF, "correct": [0, 1]}, "text_answer_multi_correct"),
        ({**TF, "options": ["Yes", "yes "]}, "ambiguous_option_text"),
        ({"options": ["a", "b"]}, "invalid_spec"),
        ({"options": ["a", "b"], "correct": [0], "extra": 1}, "invalid_spec"),
        ({"options": ["a", "b"], "correct": [True]}, "invalid_spec"),
        ({"options": ["a", "b"], "correct": ["0"]}, "invalid_spec"),
        ({**MC, "answer_by": "letter"}, "invalid_spec"),
    ],
)
def test_choice_spec_issues(spec: dict, code: str) -> None:
    assert code in codes(CHOICE.check_spec(spec))


@pytest.mark.parametrize(
    "spec",
    [
        {"options": ["a", "b"], "correct": [2]},
        {"options": ["a", "b"], "correct": []},
        {"options": ["a", "b"]},
        {"options": ["a", "b"], "correct": [0], "extra": 1},
    ],
)
def test_ungradable_choice_spec_raises(spec: dict) -> None:
    with pytest.raises(SpecError):
        CHOICE.grade(spec, "0")


def test_non_blocking_choice_issues_still_grade() -> None:
    # Gradable today (one option; an empty option text), so grading must still work.
    assert CHOICE.grade({"options": ["a"], "correct": [0]}, "0").score == 1.0
    assert CHOICE.grade({"options": ["a", ""], "correct": [0]}, "0").score == 1.0


# ---------------------------------------------------------------------------- ordering: grading


def test_parsons_newline_layout_with_indents() -> None:
    answer = "def\n    loop\n        body\n    ret\n"
    assert ORDERING.grade(PARSONS, answer) == GradeResult(
        score=1.0, feedback="Return after the loop."
    )


def test_parsons_tabs_are_one_level_each() -> None:
    assert ORDERING.grade(PARSONS, "def\n\tloop\n\t\tbody\n\tret").score == 1.0
    assert ORDERING.grade(PARSONS, "def\r\n\tloop\r\n  \t  body\r\n\tret").score == 1.0


def test_parsons_partial_indent_rounds_down() -> None:
    # 7 leading spaces is level 1, not 2.
    assert ORDERING.grade(PARSONS, "def\n    loop\n       body\n    ret").score == 0.0
    assert ORDERING.grade(PARSONS, "def\n     loop\n         body\n       ret").score == 1.0


def test_parsons_wrong_indent_or_order() -> None:
    assert ORDERING.grade(PARSONS, "def\nloop\nbody\nret").score == 0.0
    result = ORDERING.grade(PARSONS, "def\n    loop\n    ret\n        body")
    assert result.score == 0.0
    assert result.format_error is None
    assert result.feedback == "Return after the loop."


def test_parsons_comma_list_is_all_indent_zero() -> None:
    assert ORDERING.grade(FLAT, "a,b,c").score == 1.0
    assert ORDERING.grade(FLAT, " a , b ,c ").score == 1.0
    assert ORDERING.grade(FLAT, "a,c,b").score == 0.0
    # Indented content can never be expressed as a comma list.
    assert ORDERING.grade(PARSONS, "def,loop,body,ret").score == 0.0


def test_parsons_comma_with_newline_is_a_line_layout() -> None:
    # A comma plus a newline is the line form, so "a,b" is one (unknown) block id.
    assert ORDERING.grade(FLAT, "a,b\nc").score == 0.0
    assert ORDERING.grade(FLAT, "a\nb\nc").score == 1.0
    assert ORDERING.grade(FLAT, "\n\na\n  \nb\nc\n\n").score == 1.0


def test_check_indent_false_compares_ids_only() -> None:
    lax = {**PARSONS, "check_indent": False}
    assert ORDERING.grade(lax, "def\nloop\nbody\nret").score == 1.0
    assert ORDERING.grade(lax, "def,loop,body,ret").score == 1.0
    assert ORDERING.grade(lax, "def\nbody\nloop\nret").score == 0.0


@pytest.mark.parametrize("answer", ["", "   ", "\n\n", ",", " , "])
def test_parsons_empty_answer_is_unreadable(answer: str) -> None:
    result = ORDERING.grade(PARSONS, answer)
    assert result.score == 0.0
    assert result.format_error
    assert result.feedback == "Return after the loop."


# --------------------------------------------------------------------------- ordering: the spec


def test_good_ordering_specs_have_no_issues() -> None:
    assert ORDERING.check_spec(PARSONS) == []
    assert ORDERING.check_spec(FLAT) == []


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        ({**FLAT, "correct_order": ["a", "z"]}, "unknown_block"),
        ({**FLAT, "blocks": [*FLAT["blocks"], {"id": "a", "indent": 1}]}, "duplicate_block"),
        ({**FLAT, "blocks": [{"id": "a", "indent": -1}]}, "negative_indent"),
        ({**FLAT, "blocks": []}, "no_blocks"),
        ({**FLAT, "correct_order": []}, "empty_order"),
        (
            {"blocks": [{"id": " a", "indent": 0}], "correct_order": [" a"]},
            "reference_not_full_marks",
        ),
        (
            {"blocks": [{"id": "x,y", "indent": 0}], "correct_order": ["x,y"]},
            "reference_not_full_marks",
        ),
        ({"blocks": [{"id": "a"}], "correct_order": "a"}, "invalid_spec"),
        ({**FLAT, "blocks": [{"id": "a", "indent": 0, "code": "x"}]}, "invalid_spec"),
        ({**FLAT, "blocks": [{"id": "a", "indent": True}]}, "invalid_spec"),
        ({**FLAT, "blocks": [{"id": 1, "indent": 0}]}, "invalid_spec"),
    ],
)
def test_ordering_spec_issues(spec: dict, code: str) -> None:
    assert code in codes(ORDERING.check_spec(spec))


@pytest.mark.parametrize(
    "spec",
    [
        {**FLAT, "correct_order": ["a", "z"]},
        {**FLAT, "blocks": [{"id": "a", "indent": -1}], "correct_order": ["a"]},
        {**FLAT, "correct_order": []},
        {**FLAT, "blocks": []},
        {"blocks": "nope", "correct_order": ["a"]},
    ],
)
def test_ungradable_ordering_spec_raises(spec: dict) -> None:
    with pytest.raises(SpecError):
        ORDERING.grade(spec, "a")


def test_duplicate_block_ids_still_grade_with_the_last_indent() -> None:
    spec = {"blocks": [{"id": "a", "indent": 0}, {"id": "a", "indent": 1}], "correct_order": ["a"]}
    assert ORDERING.grade(spec, "    a").score == 1.0


# ------------------------------------------- parity with the frozen pre-move scorer (the oracle)


def _app_score(question_type: str, content: dict, answer: str) -> float:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from grading_oracle import score_answer

    from app.domain.enums import QuestionType
    from app.domain.questions import Question

    question = Question(question_type=QuestionType(question_type), prompt="q", content=content)
    return score_answer(question, answer).score


MC_CONTENT = {"options": ["a", "b", "c", "d"], "correct_option_index": 2, "explanation": "c."}
TF_CONTENT = {"correct_answer": False, "explanation": "No."}
PARSONS_CONTENT = {
    "blocks": PARSONS["blocks"],
    "correct_order": PARSONS["correct_order"],
    "explanation": "e",
}


@pytest.mark.parametrize("answer", ["2", " 2 ", "+2", "1", "9", "-1", "", "c", "2.0", "0,2"])
def test_parity_multiple_choice(answer: str) -> None:
    spec = {"options": MC_CONTENT["options"], "correct": [2], "explanation": "c."}
    assert CHOICE.grade(spec, answer).score * 100 == _app_score(
        "multiple_choice", MC_CONTENT, answer
    )


@pytest.mark.parametrize("answer", ["false", " FALSE\n", "true", "True", "0", "1", "", "no"])
def test_parity_true_false(answer: str) -> None:
    spec = {"options": ["true", "false"], "correct": [1], "answer_by": "text"}
    assert CHOICE.grade(spec, answer).score * 100 == _app_score("true_false", TF_CONTENT, answer)


@pytest.mark.parametrize(
    "answer",
    [
        "def\n    loop\n        body\n    ret",
        "def\n\tloop\n\t\tbody\n\tret\n",
        "def\r\n\tloop\r\n\t\tbody\r\n\tret",
        "def\nloop\nbody\nret",
        "def,loop,body,ret",
        "def\n     loop\n         body\n       ret",
        "def\n    loop\n    ret\n        body",
        "",
        "def,loop\nbody,ret",
    ],
)
def test_parity_parsons(answer: str) -> None:
    assert ORDERING.grade(PARSONS, answer).score * 100 == _app_score(
        "parsons", PARSONS_CONTENT, answer
    )


def test_parity_parsons_flat_comma() -> None:
    content = {"blocks": FLAT["blocks"], "correct_order": FLAT["correct_order"]}
    for answer in ["a,b,c", " a , b ,c ", "a,c,b", "a\nb\nc", "a,b\nc"]:
        assert ORDERING.grade(FLAT, answer).score * 100 == _app_score("parsons", content, answer)
