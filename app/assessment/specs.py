"""From a stored question to a grader call (C5): which capability grades it, with what spec.

The graders in ``graders/`` know nothing about question types or the database; this module is
the one place that translates. Each of the seven question types maps its stored ``content`` to
one capability's spec, plus a rewrite of the student's answer into that grader's convention
(true/false is a two-option choice, so ``"true"`` becomes index ``"0"``).

The translation is meant to change no score: ``tests/test_grader_replay.py`` replays stored
attempts through the old scorer and through this path and requires them to agree.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domain.enums import QuestionType

#: The answer as the student typed it -> the answer in the grader's convention.
AnswerRewrite = Callable[[str], str]


@dataclass(frozen=True)
class GradingPlan:
    capability: str
    spec: dict[str, Any]
    rewrite_answer: AnswerRewrite


class Unmarkable(Exception):
    """The stored content lacks what grading requires (a defect in the question)."""


def _explanation(content: dict) -> str | None:
    text = content.get("explanation")
    return text if isinstance(text, str) and text.strip() else None


def _same(answer: str) -> str:
    return answer


def _true_false_answer(answer: str) -> str:
    submitted = answer.strip().casefold() if isinstance(answer, str) else ""
    return {"true": "0", "false": "1"}.get(submitted, "not an option")


def plan_for(question_type: QuestionType, content: dict, tests: object = None) -> GradingPlan:
    """The capability, spec and answer rewrite for one stored question.

    ``tests`` is the question's ``tests`` column, used when ``content`` carries none.

    Raises:
        Unmarkable: the content is missing what this type needs.
    """
    explanation = _explanation(content)
    match question_type:
        case QuestionType.MULTIPLE_CHOICE:
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
                    "explanation": explanation,
                },
                _same,
            )
        case QuestionType.TRUE_FALSE:
            expected = content.get("correct_answer")
            if not isinstance(expected, bool):
                raise Unmarkable("no correct answer is recorded")
            return GradingPlan(
                "structured.choice",
                {
                    "options": ["true", "false"],
                    "correct": [0 if expected else 1],
                    "explanation": explanation,
                },
                _true_false_answer,
            )
        case QuestionType.OUTPUT_PREDICTION:
            expected = content.get("expected_output")
            if not isinstance(expected, str):
                raise Unmarkable("no expected output is recorded")
            return GradingPlan(
                "text.normalized_match",
                {"expected": expected, "explanation": explanation},
                _same,
            )
        case QuestionType.PARSONS:
            return GradingPlan("structured.ordering", _parsons_spec(content, explanation), _same)
        case QuestionType.CODE_COMPLETION | QuestionType.DEBUGGING | QuestionType.CODING:
            cases = _test_cases(content.get("tests")) or _test_cases(tests)
            if not cases:
                raise Unmarkable("no usable test cases are stored")
            # The app's own per-run limit, as the old runner used, so scores do not move.
            from app.config import get_settings

            return GradingPlan(
                "code.python.tests",
                {"tests": cases, "timeout_s": get_settings().validation_timeout_seconds},
                _same,
            )
    raise Unmarkable(f"no grading is defined for {question_type!r}")


def _parsons_spec(content: dict, explanation: str | None) -> dict[str, Any]:
    correct_order = content.get("correct_order")
    if not isinstance(correct_order, list) or not correct_order:
        raise Unmarkable("no correct block order is recorded")
    blocks = content.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise Unmarkable("no blocks are recorded")
    by_id = {
        str(block.get("id")): block
        for block in blocks
        if isinstance(block, dict) and block.get("id") is not None
    }
    # Only the blocks in the solution: a distractor needs no indentation to be wrong.
    spec_blocks = []
    for block_id in correct_order:
        block = by_id.get(str(block_id))
        indent = block.get("indent") if isinstance(block, dict) else None
        if not isinstance(indent, int) or isinstance(indent, bool) or indent < 0:
            raise Unmarkable(f"block {block_id!r} has no valid indentation recorded")
        spec_blocks.append({"id": str(block_id), "indent": indent})
    return {
        "blocks": spec_blocks,
        "correct_order": [str(block_id) for block_id in correct_order],
        "explanation": explanation,
    }


def _test_cases(raw: object) -> list[dict[str, Any]] | None:
    """Stored test cases as grader spec entries, or ``None`` if unusable.

    Uses the app's own reader so "usable" means exactly what it meant before.
    """
    from app.validation.runner import parse_test_cases

    cases = parse_test_cases(raw)
    if cases is None:
        return None
    return [
        {"stdin": case.stdin, "stdout": case.stdout, "assert": case.assert_code} for case in cases
    ]
