from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.domain.enums import QuestionKind, QuestionType
from app.generation.schemas import (
    RESPONSE_MODEL_FOR,
    CodingDraft,
    DebuggingDraft,
    MultipleChoiceDraft,
    OutputPredictionDraft,
    ParsonsBlock,
    ParsonsDraft,
    TrueFalseDraft,
    encode_content,
    prompt_fields_from_draft,
    scoring_kind_for,
)


def test_all_seven_types_have_response_models() -> None:
    assert set(RESPONSE_MODEL_FOR) == set(QuestionType)


@pytest.mark.parametrize(
    ("qtype", "kind"),
    [
        (QuestionType.MULTIPLE_CHOICE, QuestionKind.DISCRETE),
        (QuestionType.TRUE_FALSE, QuestionKind.DISCRETE),
        (QuestionType.OUTPUT_PREDICTION, QuestionKind.DISCRETE),
        (QuestionType.PARSONS, QuestionKind.DISCRETE),
        (QuestionType.CODE_COMPLETION, QuestionKind.TESTABLE_PROGRAM),
        (QuestionType.DEBUGGING, QuestionKind.TESTABLE_PROGRAM),
        (QuestionType.CODING, QuestionKind.TESTABLE_PROGRAM),
    ],
)
def test_scoring_kind_mapping(qtype: QuestionType, kind: QuestionKind) -> None:
    assert scoring_kind_for(qtype) is kind


def test_multiple_choice_requires_options_and_answer() -> None:
    draft = MultipleChoiceDraft(
        prompt="What does s[1:3] return for s='abcd'?",
        options=["ab", "bc", "cd", "abc"],
        correct_option_index=1,
        explanation="Slice end is exclusive.",
    )
    assert draft.correct_option_index == 1


def test_multiple_choice_rejects_correct_index_outside_options() -> None:
    with pytest.raises(ValidationError, match="correct_option_index"):
        MultipleChoiceDraft(
            prompt="What does s[1:3] return for s='abcd'?",
            options=["ab", "bc"],
            correct_option_index=2,
            explanation="Slice end is exclusive.",
        )


def test_output_prediction_requires_expected_output() -> None:
    with pytest.raises(ValidationError):
        OutputPredictionDraft(
            prompt="What prints?",
            code="print(1 + 2)",
            expected_output="",
            explanation="Addition.",
        )


def test_parsons_supports_order_and_indent() -> None:
    draft = ParsonsDraft(
        prompt="Arrange the function.",
        blocks=[
            ParsonsBlock(id="a", text="def f(x):", indent=0),
            ParsonsBlock(id="b", text="return x + 1", indent=1),
        ],
        correct_order=["a", "b"],
        explanation="Body is indented.",
    )
    assert draft.blocks[1].indent == 1


def test_coding_requires_tests() -> None:
    draft = CodingDraft(
        prompt="Write add(a, b).",
        reference_solution="def add(a, b):\n    return a + b",
        tests=[{"stdin": "", "call": "add(1, 2)", "expected": "3"}],
        explanation="Simple addition.",
    )
    assert len(draft.tests) >= 1


def test_parsons_rejects_unknown_order_id() -> None:
    with pytest.raises(ValidationError):
        ParsonsDraft(
            prompt="x",
            blocks=[ParsonsBlock(id="a", text="pass", indent=0)],
            correct_order=["a", "missing"],
            explanation="x",
        )


def test_prompt_fields_from_true_false_draft() -> None:
    draft = TrueFalseDraft(
        prompt="Strings are immutable.",
        correct_answer=True,
        explanation="Assignment to str items fails.",
    )
    prompt, reference, tests = prompt_fields_from_draft(draft)
    assert prompt == "Strings are immutable."
    assert reference == "true"
    assert tests is None


def test_prompt_fields_from_testable_draft() -> None:
    draft = DebuggingDraft(
        prompt="Find the bug.",
        code="s = 'ab'\ns[0] = 'c'",
        reference_solution="Build a new string.",
        tests=[{"call": "explain", "expected": "TypeError"}],
        explanation="Item assignment on str fails.",
    )
    prompt, reference, tests = prompt_fields_from_draft(draft)
    assert prompt == "Find the bug."
    assert reference == "Build a new string."
    assert json.loads(tests or "") == [{"call": "explain", "expected": "TypeError"}]


def test_prompt_fields_from_parsons_draft() -> None:
    draft = ParsonsDraft(
        prompt="Arrange the function.",
        blocks=[
            ParsonsBlock(id="a", text="def f(x):", indent=0),
            ParsonsBlock(id="b", text="return x + 1", indent=1),
        ],
        correct_order=["a", "b"],
        explanation="Body is indented.",
    )
    prompt, reference, tests = prompt_fields_from_draft(draft)
    assert prompt == "Arrange the function."
    assert tests is None
    parsed = json.loads(reference or "")
    assert parsed["correct_order"] == ["a", "b"]
    assert parsed["indents"] == {"a": 0, "b": 1}


def test_encode_content_includes_draft_and_metadata() -> None:
    draft = OutputPredictionDraft(
        prompt="What prints?",
        code="print(1 + 2)",
        expected_output="3",
        explanation="Addition.",
    )
    content = encode_content(
        draft,
        sources=[{"section_id": 7, "citation": "Book, ch.1, sec.2"}],
        model="fake/test-model",
    )
    parsed = json.loads(content)
    assert parsed["expected_output"] == "3"
    assert parsed["sources"][0]["section_id"] == 7
    assert parsed["model"] == "fake/test-model"
