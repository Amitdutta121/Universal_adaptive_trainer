from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.enums import QuestionKind, QuestionType
from app.generation.schemas import (
    RESPONSE_MODEL_FOR,
    CodingDraft,
    MultipleChoiceDraft,
    ParsonsBlock,
    ParsonsDraft,
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
