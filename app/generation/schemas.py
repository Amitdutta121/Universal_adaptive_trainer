"""Instructor response models for base question generation.

Each draft model is the structured output schema for one :class:`~app.domain.enums.QuestionType`.
They are kept plain and field-based so Instructor can validate LLM responses without unions.

Storage encoding maps drafts into domain :class:`~app.domain.questions.Question` fields and
its ``content`` object.
"""

from __future__ import annotations

import hashlib
import random
import re

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


#: An option letter in an explanation: "option B", "choice (C)", "answer D", or "(A)".
_LETTER_REFERENCE = re.compile(
    r"\b((?i:option|choice|answer)\s+\(?)([A-Z])(\)?)(?!\w)|(\()([A-Z])(\))"
)


def shuffle_options(draft: MultipleChoiceDraft) -> MultipleChoiceDraft:
    """The draft with its options in an order seeded by the prompt, answer index following.

    Models put the correct answer first far more often than chance (7 of 9 at A in one
    round); the drift check only reports that. The seed is the prompt's hash, so the same
    draft always shuffles the same way. Letter references in the explanation ("option B",
    "(B)") are rewritten to the new letters in one pass; other text is untouched.
    """
    count = len(draft.options)
    order = list(range(count))
    seed = int(hashlib.sha256(draft.prompt.encode("utf-8")).hexdigest()[:16], 16)
    random.Random(seed).shuffle(order)
    new_letter = {chr(ord("A") + old): chr(ord("A") + new) for new, old in enumerate(order)}

    def relabel(match: re.Match[str]) -> str:
        prefix, letter, suffix = (
            match.group(1, 2, 3) if match.group(2) is not None else match.group(4, 5, 6)
        )
        return f"{prefix}{new_letter.get(letter, letter)}{suffix}"

    return draft.model_copy(
        update={
            "options": [draft.options[old] for old in order],
            "correct_option_index": order.index(draft.correct_option_index),
            "explanation": _LETTER_REFERENCE.sub(relabel, draft.explanation),
        }
    )


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
