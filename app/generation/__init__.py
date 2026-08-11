"""Question generation boundary.

Responsibility
    Produce assessment questions for a requested subtopic and difficulty,
    grounded in the approved curriculum and the ingested books.

Status
    **Not implemented in this task.** Only the seam exists.

Key rules
    * A generation request always carries an *approved* curriculum version id
      and a subtopic id from that version. Generation without an approved
      curriculum is an error, not a fallback.
    * Every generator identifies itself with a
      :class:`GeneratorDescriptor` (kind + name + version), which is stamped on
      each produced question. Base and personalized generators must therefore
      remain distinguishable in stored data.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.llm``, ``app.persistence``.
    Must not import ``app.adaptive`` or ``app.web``.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.domain.enums import Difficulty, GeneratorKind, QuestionKind
from app.domain.questions import Question
from app.errors import FeatureNotAvailableError


class GeneratorDescriptor(BaseModel):
    """Identity of a generator, stamped onto every question it produces."""

    kind: GeneratorKind = GeneratorKind.BASE
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)

    def label(self) -> str:
        return f"{self.kind.value}:{self.name}@{self.version}"


class GenerationRequest(BaseModel):
    """What to generate. Curriculum ids are required, not optional."""

    curriculum_version_id: int
    subtopic_id: int
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


class NullQuestionGenerator:
    """Placeholder generator. Raises so no unvalidated content is invented."""

    @property
    def descriptor(self) -> GeneratorDescriptor:
        return GeneratorDescriptor(kind=GeneratorKind.BASE, name="null", version="0")

    def generate(self, request: GenerationRequest) -> list[Question]:
        raise FeatureNotAvailableError(
            "Question generation is not implemented yet.",
            detail=f"Requested {request.count} question(s) for subtopic {request.subtopic_id}.",
        )


def get_question_generator(professor_id: int | None = None) -> QuestionGenerator:
    """Return the generator to use.

    Will later return a personalized generator when one exists for
    ``professor_id`` and fall back to the base generator otherwise.
    """
    return NullQuestionGenerator()
