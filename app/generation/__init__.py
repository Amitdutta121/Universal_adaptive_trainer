"""Question generation boundary.

Responsibility
    Produce assessment questions for a requested subtopic and difficulty,
    grounded in the approved curriculum and the ingested books.

Status
    The section-first base generator is implemented. Personalized generation is
    deferred; callers use :class:`GenerationService` for persisted generation.

Key rules
    * A generation request always carries an *approved* curriculum version id
      and a subtopic id from that version. Generation without an approved
      curriculum is an error, not a fallback.
    * Every generator identifies itself with a
      :class:`GeneratorDescriptor` (kind + name + version), which is stamped on
      each produced question. Base and personalized generators must therefore
      remain distinguishable in stored data.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.evaluation``, ``app.ingestion``,
    ``app.llm``, ``app.persistence``, ``app.validation``.
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
    Its ``subtopic_id`` maps to the single-item ``QuestionSpec.subtopic_ids``.
    """

    curriculum_version_id: int
    subtopic_id: int
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

    ``professor_id`` remains reserved for the future personalized path. The LLM
    client is not constructed here, so an application can start without its
    credentials. ``generate`` requires a generator constructed with ``session``;
    use ``BaseQuestionGenerator(session=...)`` for unpersisted questions or
    :class:`GenerationService` to persist them.
    """
    del professor_id
    from app.generation.base import BaseQuestionGenerator

    return BaseQuestionGenerator()


from app.generation.base import BaseQuestionGenerator  # noqa: E402
from app.generation.service import GenerationService  # noqa: E402

__all__ = [
    "BaseQuestionGenerator",
    "GenerationRequest",
    "GenerationService",
    "GeneratorDescriptor",
    "QuestionGenerator",
    "get_question_generator",
]
