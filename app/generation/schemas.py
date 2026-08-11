"""Instructor response models for base question generation.

Each draft model is the structured output schema for one :class:`~app.domain.enums.QuestionType`.
They are kept plain and field-based so Instructor can validate LLM responses without unions.

Storage encoding and mapping into domain :class:`~app.domain.questions.Question` fields is
handled in a later task.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import QuestionKind, QuestionType


def scoring_kind_for(question_type: QuestionType) -> QuestionKind:
    """Map assessment format to the fixed scoring mode for that type."""
    if question_type in {
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.OUTPUT_PREDICTION,
        QuestionType.PARSONS,
    }:
        return QuestionKind.DISCRETE
    return QuestionKind.TESTABLE_PROGRAM


class MultipleChoiceDraft(BaseModel):
    """Multiple-choice question draft."""

    prompt: str = Field(min_length=1)
    options: list[str] = Field(min_length=2)
    correct_option_index: int = Field(ge=0)
    explanation: str = Field(min_length=1)


class TrueFalseDraft(BaseModel):
    """True/false question draft."""

    prompt: str = Field(min_length=1)
    correct_answer: bool
    explanation: str = Field(min_length=1)


class OutputPredictionDraft(BaseModel):
    """Output-prediction question draft."""

    prompt: str = Field(min_length=1)
    code: str = Field(min_length=1)
    expected_output: str
    explanation: str = Field(min_length=1)


class CodeCompletionDraft(BaseModel):
    """Code-completion question draft."""

    prompt: str = Field(min_length=1)
    code: str = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    tests: list[dict[str, str]] = Field(min_length=1)
    explanation: str = Field(min_length=1)


class DebuggingDraft(BaseModel):
    """Debugging question draft."""

    prompt: str = Field(min_length=1)
    code: str = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    tests: list[dict[str, str]] = Field(min_length=1)
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
    tests: list[dict[str, str]] = Field(min_length=1)
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
