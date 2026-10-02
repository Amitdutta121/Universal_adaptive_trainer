"""Instructor response models for base question generation.

Each draft model is the structured output schema for one :class:`~app.domain.enums.QuestionType`.
They are kept plain and field-based so Instructor can validate LLM responses without unions.

Storage encoding maps drafts into domain :class:`~app.domain.questions.Question` fields and
its ``content`` object.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import QuestionKind, QuestionType


def scoring_kind_for(question_type: QuestionType) -> QuestionKind:
    """Map assessment format to the fixed scoring mode for that type (its module's)."""
    from app.question_types import get_type

    return get_type(question_type).kind


def response_model_for(question_type: QuestionType) -> type[TaxonomyClaim]:
    """The structured-output schema the LLM must return for this type (its module's)."""
    from app.question_types import get_type

    return get_type(question_type).draft_model


class TaxonomyClaim(BaseModel):
    """The topic and subtopics the generator says its question exercises.

    Every draft carries these because the professor no longer supplies them: the
    generator is given the whole approved taxonomy and classifies its own output.
    The ids are unverified here -- :func:`~app.generation.spec.resolve_claimed_taxonomy`
    is what decides whether they name anything real.
    """

    topic_id: int = Field(
        description="Numeric id of the single topic this question belongs to.",
    )
    subtopic_ids: list[int] = Field(
        min_length=1,
        description=(
            "Numeric ids of the subtopics this question exercises. All must be "
            "subtopics of the chosen topic. Name only the subtopics the question "
            "actually assesses."
        ),
    )


class MultipleChoiceDraft(TaxonomyClaim):
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


class TrueFalseDraft(TaxonomyClaim):
    """True/false question draft."""

    prompt: str = Field(min_length=1)
    correct_answer: bool
    explanation: str = Field(min_length=1)


class OutputPredictionDraft(TaxonomyClaim):
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


class CodeCompletionDraft(TaxonomyClaim):
    """Code-completion question draft."""

    prompt: str = Field(min_length=1)
    code: str = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    tests: list[ExecutableTestCase] = Field(min_length=1)
    explanation: str = Field(min_length=1)


class DebuggingDraft(TaxonomyClaim):
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


class ParsonsDraft(TaxonomyClaim):
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


class CodingDraft(TaxonomyClaim):
    """Open coding question draft."""

    prompt: str = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    tests: list[ExecutableTestCase] = Field(min_length=1)
    explanation: str = Field(min_length=1)


def prompt_fields_from_draft(draft: BaseModel) -> tuple[str, str | None, str | None]:
    """Map a validated draft into legacy prompt columns for edit/review invariants."""
    from app.question_types import type_for_draft

    columns = type_for_draft(draft).columns_from_draft(draft)
    return columns.prompt, columns.reference_solution, columns.tests


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
