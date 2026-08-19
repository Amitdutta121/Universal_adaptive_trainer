"""Question generation boundary.

Responsibility
    Produce assessment questions for a requested source section, difficulty and
    format, grounded in the approved curriculum and the ingested books, and
    classify each one into the taxonomy.

Status
    The section-first base generator and personalized-context generator are
    implemented. :class:`GenerationService` selects between them via an explicit
    ``generator`` flag; callers use it for persisted generation.

Key rules
    * A generation request always carries an *approved* curriculum version id.
      Generation without an approved curriculum is an error, not a fallback.
    * The request does **not** name a topic or subtopic. The generator receives
      the whole approved taxonomy and classifies its own question, and the claim
      is validated against that taxonomy before the question is stored.
    * Every generator identifies itself with a
      :class:`GeneratorDescriptor` (kind + name + version), which is stamped on
      each produced question. Base and personalized generators must therefore
      remain distinguishable in stored data.
    * Generator selection is explicit on :meth:`GenerationService.generate_for_sections`
      (``generator="base"`` or ``"personalized"``). The UI flag drives selection;
      ``professor_id`` on :class:`GenerationRequest` is reserved and does not
      switch generators here.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.evaluation``, ``app.ingestion``,
    ``app.llm``, ``app.persistence``, ``app.personalization``, ``app.validation``.
    Must not import ``app.adaptive`` or ``app.web``.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.domain.enums import Difficulty, GeneratorKind, QuestionKind, QuestionType
from app.domain.questions import Question


class GeneratorDescriptor(BaseModel):
    """Identity of a generator, stamped onto every question it produces."""

    kind: GeneratorKind = GeneratorKind.BASE
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)

    def label(self) -> str:
        return f"{self.kind.value}:{self.name}@{self.version}"


class GenerationRequest(BaseModel):
    """Public request shape for unpersisted, section-first base generation.

    ``BaseQuestionGenerator.generate`` makes one question for each supplied
    source section; ``count`` is retained for generator-selection compatibility.

    Carries no subtopic: the professor chooses the source, the difficulty and
    the format, and the generator decides which part of the taxonomy the section
    can actually assess.
    """

    curriculum_version_id: int
    question_type: QuestionType
    source_section_ids: list[int] = Field(min_length=1)
    difficulty: Difficulty
    kind: QuestionKind = QuestionKind.TESTABLE_PROGRAM
    count: int = Field(default=1, ge=1, le=50)
    #: Set when generating on behalf of a specific professor's learned
    #: preferences; ``None`` means use the base generator.
    professor_id: int | None = None


class QuestionGenerator(Protocol):
    """Generates questions for a request."""

    @property
    def descriptor(self) -> GeneratorDescriptor: ...

    def generate(self, request: GenerationRequest) -> list[Question]: ...


def get_question_generator(professor_id: int | None = None):
    """Return an unconfigured base generator for descriptor and selection checks.

    ``professor_id`` is ignored for v1: generator selection happens explicitly
    on :meth:`GenerationService.generate_for_sections` via the ``generator``
    flag (UI-driven), not through this helper. The LLM client is not constructed
    here, so an application can start without its credentials. ``generate``
    requires a generator constructed with ``session``; use
    ``BaseQuestionGenerator(session=...)`` for unpersisted questions or
    :class:`GenerationService` to persist them.
    """
    del professor_id
    from app.generation.base import BaseQuestionGenerator

    return BaseQuestionGenerator()


from app.generation.base import BaseQuestionGenerator  # noqa: E402
from app.generation.batch import (  # noqa: E402
    ChunkQuestionRequest,
    PlannedQuestion,
    compile_chunk_requests,
    count_identical_requests,
)
from app.generation.service import GenerationService  # noqa: E402

__all__ = [
    "BaseQuestionGenerator",
    "ChunkQuestionRequest",
    "GenerationRequest",
    "GenerationService",
    "GeneratorDescriptor",
    "PlannedQuestion",
    "QuestionGenerator",
    "compile_chunk_requests",
    "count_identical_requests",
    "get_question_generator",
]
