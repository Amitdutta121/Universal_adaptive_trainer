"""The contract between this application and the model, in both directions.

Every LLM call in curriculum proposal is a structured call: the model is handed
the JSON Schema of one of these types and must answer with an object that
satisfies it. Validation is strict for the same reason the book document contract
is strict (ADR-015) -- ``extra="forbid"`` means a field the model invented is an
error rather than a silently ignored key, and a response that does not validate
is rejected whole rather than repaired.

Two stages, two schemas
    :class:`SectionAnalysis` is Stage A: what one instructional section teaches,
    and the assessable concepts it introduces. :class:`NormalizationResult` is
    Stage B: how the candidate concepts gathered from every book consolidate into
    one Topic -> Subtopic vocabulary.

Granularity is a schema concern, not only a prompt concern
    A subtopic becomes a weakness dimension in the adaptive engine, so "every
    noun in the chapter" is a failure mode with real consequences: weakness
    spread over hundreds of micro-concepts never accumulates enough evidence to
    steer selection. :data:`MAX_CONCEPTS_PER_SECTION` puts a hard ceiling on how
    finely one section may be split, so a model that ignores the instruction is
    caught by validation rather than trusted.
"""

from __future__ import annotations

from typing import Annotated, Any, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.domain.enums import ConceptConfidence
from app.errors import MalformedModelOutputError

#: Identifies the Stage A procedure. Stored on every proposal, so results stay
#: comparable after the prompt or schema changes.
STAGE_A_VERSION = "section-analysis/1"
STAGE_B_VERSION = "cross-book-normalization/1"

#: One section may introduce several assessable concepts, but not a dozen. See
#: the module docstring: this is the guard against micro-concept explosion.
MAX_CONCEPTS_PER_SECTION = 6

#: Short excerpts, not whole sections. Evidence exists so a professor can see
#: what the analysis was looking at, and long quotes defeat that.
Excerpt = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
Label = Annotated[str, StringConstraints(min_length=1, max_length=300)]
CandidateId = Annotated[str, StringConstraints(min_length=1, max_length=32)]

ModelT = TypeVar("ModelT", bound=BaseModel)


class CandidateConcept(BaseModel):
    """One assessable instructional concept a section teaches.

    "Candidate" because this is one book's wording of it. Stage B decides which
    candidates across which books are the same concept.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    #: This book's own way of naming the skill, e.g. "Accessing characters".
    label: Label
    #: The broader area it belongs to, e.g. "Strings". Stage B normalises it.
    topic_label: Label
    #: What a student who has mastered it can do. One or two sentences.
    definition: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    #: Excerpts or examples from *this* section that show the concept being
    #: taught. Required: a concept with no support in the text is an assertion,
    #: and the professor would have no way to check it.
    evidence: list[Excerpt] = Field(min_length=1, max_length=4)
    confidence: ConceptConfidence


class SectionAnalysis(BaseModel):
    """Stage A: the instructional content of one section."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    #: What this section teaches, in the analysis's own words.
    teaches: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    #: False for front matter, exercise lists, indexes and similar: text that
    #: belongs to a textbook but teaches no assessable skill of its own.
    is_instructional: bool
    #: May be empty even for instructional prose -- a section that only motivates
    #: or recaps should contribute nothing rather than be forced to yield a
    #: concept.
    concepts: list[CandidateConcept] = Field(
        default_factory=list, max_length=MAX_CONCEPTS_PER_SECTION
    )
    confidence: ConceptConfidence

    @model_validator(mode="after")
    def _non_instructional_sections_propose_nothing(self) -> SectionAnalysis:
        """Reject the contradiction rather than silently preferring one field.

        A response claiming a section teaches nothing *and* listing concepts it
        teaches is not a response this application knows how to interpret.
        """
        if not self.is_instructional and self.concepts:
            raise ValueError(
                "a section marked is_instructional=false must not propose any concepts"
            )
        return self


class ConceptGroup(BaseModel):
    """Stage B: candidates from any number of books judged to be one concept."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    normalized_topic: Label
    normalized_subtopic: Label
    normalized_description: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    #: Why these candidates are the same concept, in one auditable sentence.
    #: This is what a professor reads to decide whether the merge was justified.
    reason_for_grouping: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    confidence: ConceptConfidence
    #: The candidate ids this group consolidates. Checked against the ids that
    #: were actually sent -- see :mod:`app.curriculum.normalization`.
    candidate_ids: list[CandidateId] = Field(min_length=1)


class NormalizationResult(BaseModel):
    """Stage B: the whole consolidated vocabulary."""

    model_config = ConfigDict(extra="forbid")

    groups: list[ConceptGroup] = Field(min_length=1)


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """The JSON Schema handed to the model for a structured call."""
    return model.model_json_schema()


def parse_structured(model: type[ModelT], payload: dict[str, Any], *, stage: str) -> ModelT:
    """Validate a model's raw response against ``model``.

    Raises:
        MalformedModelOutputError: if the payload does not satisfy the schema.
            Never repaired: a partially understood analysis would put invented
            curriculum structure in front of the professor, indistinguishable
            from analysis that actually worked.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise MalformedModelOutputError(
            f"The model's {stage} response did not match the requested schema.",
            detail=describe_validation_error(exc),
        ) from exc


def describe_validation_error(error: ValidationError, limit: int = 8) -> str:
    """Render pydantic's errors as a short, field-by-field explanation."""
    parts: list[str] = []
    for problem in error.errors()[:limit]:
        location = ".".join(str(piece) for piece in problem["loc"]) or "(response root)"
        parts.append(f"{location}: {problem['msg']}")
    remaining = len(error.errors()) - len(parts)
    if remaining > 0:
        parts.append(f"and {remaining} more problem(s)")
    return "; ".join(parts)
