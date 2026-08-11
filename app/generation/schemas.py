"""Instructor response models for base question generation.

Each draft model is the structured output schema for one :class:`~app.domain.enums.QuestionType`.
They are kept plain and field-based so Instructor can validate LLM responses without unions.

Storage encoding maps drafts into domain :class:`~app.domain.questions.Question` fields and
its ``content`` object.
"""

from __future__ import annotations

import json
from typing import assert_never

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import QuestionKind, QuestionType


def scoring_kind_for(question_type: QuestionType) -> QuestionKind:
    """Map assessment format to the fixed scoring mode for that type."""
    match question_type:
        case (
            QuestionType.MULTIPLE_CHOICE
            | QuestionType.TRUE_FALSE
            | QuestionType.OUTPUT_PREDICTION
            | QuestionType.PARSONS
        ):
            return QuestionKind.DISCRETE
        case QuestionType.CODE_COMPLETION | QuestionType.DEBUGGING | QuestionType.CODING:
            return QuestionKind.TESTABLE_PROGRAM
        case _:
            assert_never(question_type)


class MultipleChoiceDraft(BaseModel):
    """Multiple-choice question draft."""

    prompt: str = Field(min_length=1)
    options: list[str] = Field(min_length=2)
    correct_option_index: int = Field(ge=0)
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _correct_option_index_is_within_options(self) -> MultipleChoiceDraft:
        if self.correct_option_index >= len(self.options):
            msg = "correct_option_index must refer to an option."
            raise ValueError(msg)
        return self


class TrueFalseDraft(BaseModel):
    """True/false question draft."""

    prompt: str = Field(min_length=1)
    correct_answer: bool
    explanation: str = Field(min_length=1)


class OutputPredictionDraft(BaseModel):
    """Output-prediction question draft."""

    prompt: str = Field(min_length=1)
    code: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class ExecutableTestCase(BaseModel):
    """One hybrid stdin/stdout/assert case for executable question types."""

    model_config = ConfigDict(populate_by_name=True)

    stdin: str = ""
    stdout: str | None = None
    assert_code: str | None = Field(default=None, alias="assert")

    @model_validator(mode="after")
    def _requires_stdout_or_assert(self) -> ExecutableTestCase:
        if self.stdout is None and self.assert_code is None:
            raise ValueError("each test needs stdout or assert")
        return self


class CodeCompletionDraft(BaseModel):
    """Code-completion question draft."""

    prompt: str = Field(min_length=1)
    code: str = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    tests: list[ExecutableTestCase] = Field(min_length=1)
    explanation: str = Field(min_length=1)


class DebuggingDraft(BaseModel):
    """Debugging question draft."""

    prompt: str = Field(min_length=1)
    code: str = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    tests: list[ExecutableTestCase] = Field(min_length=1)
    explanation: str = Field(min_length=1)


class ParsonsBlock(BaseModel):
    """One Parsons puzzle block with display text and indent level."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    indent: int = Field(ge=0)


class ParsonsDraft(BaseModel):
    """Parsons (code ordering) question draft."""

    prompt: str = Field(min_length=1)
    blocks: list[ParsonsBlock] = Field(min_length=1)
    correct_order: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _correct_order_refs_known_blocks(self) -> ParsonsDraft:
        block_ids = {block.id for block in self.blocks}
        unknown = [block_id for block_id in self.correct_order if block_id not in block_ids]
        if unknown:
            msg = f"correct_order references unknown block ids: {', '.join(unknown)}"
            raise ValueError(msg)
        return self


class CodingDraft(BaseModel):
    """Open coding question draft."""

    prompt: str = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    tests: list[ExecutableTestCase] = Field(min_length=1)
    explanation: str = Field(min_length=1)


RESPONSE_MODEL_FOR: dict[QuestionType, type[BaseModel]] = {
    QuestionType.MULTIPLE_CHOICE: MultipleChoiceDraft,
    QuestionType.TRUE_FALSE: TrueFalseDraft,
    QuestionType.OUTPUT_PREDICTION: OutputPredictionDraft,
    QuestionType.CODE_COMPLETION: CodeCompletionDraft,
    QuestionType.DEBUGGING: DebuggingDraft,
    QuestionType.PARSONS: ParsonsDraft,
    QuestionType.CODING: CodingDraft,
}


def prompt_fields_from_draft(draft: BaseModel) -> tuple[str, str | None, str | None]:
    """Map a validated draft into legacy prompt columns for edit/review invariants."""
    if isinstance(draft, MultipleChoiceDraft):
        return draft.prompt, draft.options[draft.correct_option_index], None
    if isinstance(draft, TrueFalseDraft):
        return draft.prompt, "true" if draft.correct_answer else "false", None
    if isinstance(draft, OutputPredictionDraft):
        return draft.prompt, draft.expected_output, None
    if isinstance(draft, ParsonsDraft):
        indents = {block.id: block.indent for block in draft.blocks}
        reference = json.dumps({"correct_order": draft.correct_order, "indents": indents})
        return draft.prompt, reference, None
    if isinstance(draft, CodeCompletionDraft | DebuggingDraft | CodingDraft):
        return (
            draft.prompt,
            draft.reference_solution,
            json.dumps([case.model_dump(mode="json", by_alias=True) for case in draft.tests]),
        )
    msg = f"Unsupported draft type: {type(draft).__name__}"
    raise TypeError(msg)


def build_content(
    draft: BaseModel,
    *,
    sources: list[dict[str, object]] | None = None,
    model: str | None = None,
) -> dict[str, object]:
    """Combine a draft with its grounding metadata for the ``content`` column."""
    payload: dict[str, object] = draft.model_dump(mode="json")
    if sources is not None:
        payload["sources"] = sources
    if model is not None:
        payload["model"] = model
    return payload
