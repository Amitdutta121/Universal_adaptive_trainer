"""Parsons: put the code blocks in order, with indentation; graded by ``structured.ordering``."""

from __future__ import annotations

import json
import random
from typing import Any

from app.assessment.specs import GradingPlan, Unmarkable
from app.domain.enums import QuestionKind, QuestionType
from app.domain.questions import QuestionCheck
from app.generation.schemas import ParsonsDraft
from app.question_types._shared import explanation, same
from app.question_types.base import DraftColumns, StudentView
from app.validation.report import make_check
from app.validation.runner import LocalCodeRunner


class Parsons:
    question_type = QuestionType.PARSONS
    kind = QuestionKind.DISCRETE
    draft_model = ParsonsDraft
    instruction = (
        "Create a Parsons puzzle. Each block must have an id, text, and correct indent level; "
        "correct_order must list the block ids in solution order."
    )

    def columns_from_draft(self, draft: ParsonsDraft) -> DraftColumns:
        indents = {block.id: block.indent for block in draft.blocks}
        reference = json.dumps({"correct_order": draft.correct_order, "indents": indents})
        return DraftColumns(draft.prompt, reference, None)

    def grading_plan(self, content: dict, tests: object) -> GradingPlan:
        del tests
        return GradingPlan("structured.ordering", _ordering_spec(content), same)

    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
        del runner
        blocks = content.get("blocks")
        order = content.get("correct_order")
        valid_blocks = (
            isinstance(blocks, list)
            and bool(blocks)
            and all(isinstance(block, dict) for block in blocks)
        )
        block_ids = [block.get("id") for block in blocks] if valid_blocks else []
        order_consistent = (
            valid_blocks
            and isinstance(order, list)
            and all(isinstance(block_id, str) for block_id in order)
            and all(isinstance(block_id, str) for block_id in block_ids)
            and len(set(block_ids)) == len(block_ids)
            and len(order) == len(block_ids)
            and len(set(order)) == len(order)
            and set(order) == set(block_ids)
        )
        indent_valid = valid_blocks and all(
            isinstance(block.get("indent"), int)
            and not isinstance(block.get("indent"), bool)
            and block["indent"] >= 0
            for block in blocks
        )

        reference_compiles = False
        evidence = None
        if order_consistent and indent_valid:
            blocks_by_id = {block["id"]: block for block in blocks}
            text_valid = all(
                isinstance(blocks_by_id[block_id].get("text"), str) for block_id in order
            )
            if text_valid:
                source = "\n".join(
                    (" " * (4 * blocks_by_id[block_id]["indent"])) + blocks_by_id[block_id]["text"]
                    for block_id in order
                )
                try:
                    compile(source, "<parsons>", "exec")
                except (SyntaxError, TypeError, ValueError) as error:
                    evidence = str(error)
                else:
                    reference_compiles = True

        return [
            make_check(
                "parsons_order_consistent",
                order_consistent,
                "Canonical order is consistent",
            ),
            make_check(
                "parsons_indent_valid",
                indent_valid,
                "Indentation representation is valid",
            ),
            make_check(
                "parsons_reference_compiles",
                reference_compiles,
                "Reconstructed reference compiles",
                evidence,
            ),
        ]

    def student_view(self, content: dict, *, seed: int) -> StudentView:
        """Blocks, shuffled.

        Stored order is the correct order, so publishing it unshuffled would answer
        the puzzle. The shuffle is seeded on the attempt id so a reload shows the
        same arrangement rather than silently re-posing the question.
        """
        blocks = content.get("blocks")
        if not isinstance(blocks, list):
            return StudentView()
        presentable = [
            {
                "id": str(block.get("id")),
                "text": str(block.get("text")),
                "indent": block.get("indent", 0) if isinstance(block.get("indent", 0), int) else 0,
            }
            for block in blocks
            if isinstance(block, dict)
            and block.get("id") is not None
            and block.get("text") is not None
        ]
        random.Random(seed).shuffle(presentable)
        return StudentView(blocks=presentable)


def _ordering_spec(content: dict) -> dict[str, Any]:
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
        "explanation": explanation(content),
    }


TYPE = Parsons()
