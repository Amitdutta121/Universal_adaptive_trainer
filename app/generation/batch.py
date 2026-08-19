"""Compiling a per-chunk question request into the questions a run will ask for.

Pure: no session, no IO, no model call. The professor's spec sheet says *how many*
questions a chunk should produce at each difficulty and *in which formats*. This
module multiplies the two out into the ordered list of
(section, difficulty, format) triples the generator is then asked for, one model
call each.

It lives apart from :mod:`app.generation.service` for two reasons: the rule that
decides which format a question gets is then testable without a database or a
provider, and the console can price a spec sheet by asking the API rather than by
restating the rule in TypeScript (ADR-027, ADR-044).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.enums import Difficulty, QuestionType
from app.errors import InvalidQuestionSpecError

#: The order a compiled run walks a chunk's difficulties. Fixed so that a plan is
#: reproducible and a professor can predict which question is generated first.
DIFFICULTY_ORDER: tuple[Difficulty, ...] = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)


@dataclass(frozen=True)
class ChunkQuestionRequest:
    """One chunk's whole instruction.

    ``counts`` is how many questions this chunk should produce at each difficulty
    *in each chosen format*; a difficulty that is absent or zero produces none.
    Two medium questions with three formats chosen is therefore six questions:
    two multiple choice, two Parsons, two coding.
    """

    section_id: int
    counts: Mapping[Difficulty, int] = field(default_factory=dict)
    question_types: Sequence[QuestionType] = ()

    @property
    def per_format_total(self) -> int:
        """How many questions this chunk asks for in each chosen format."""
        return sum(self.counts.get(difficulty, 0) for difficulty in DIFFICULTY_ORDER)

    @property
    def total(self) -> int:
        """How many questions this chunk contributes to the run, in all formats."""
        return self.per_format_total * len(self.question_types)


@dataclass(frozen=True)
class PlannedQuestion:
    """One question a compiled run will ask the generator for."""

    section_id: int
    difficulty: Difficulty
    question_type: QuestionType


def _reject_negative_counts(chunk: ChunkQuestionRequest) -> None:
    """Refuse a negative count.

    The API schema already bounds each count, but the compiler is a public entry
    point of its own and a negative here would silently produce nothing rather
    than saying what is wrong.
    """
    for difficulty, count in chunk.counts.items():
        if count < 0:
            raise InvalidQuestionSpecError(
                "A question count cannot be negative.",
                detail=f"Section {chunk.section_id} asks for {count} {difficulty.value} questions.",
            )


def compile_chunk_requests(chunks: Sequence[ChunkQuestionRequest]) -> list[PlannedQuestion]:
    """Expand per-chunk instructions into the questions to generate, in order.

    Every count applies to every chosen format, so a chunk produces
    ``(easy + medium + hard) * formats`` questions. One easy, one medium and one
    hard with two formats chosen is six questions, not three — each difficulty is
    made once in each format.

    The order is difficulty first, then format within it: easy MCQ, easy Parsons,
    medium MCQ, medium Parsons, and so on. A plan is therefore reproducible and a
    professor can predict which question is generated first.

    Raises:
        InvalidQuestionSpecError: nothing was asked for, a count is negative, or a
            chunk asks for questions without naming a format to draw them from.
    """
    if not chunks:
        raise InvalidQuestionSpecError(
            "No chunks were selected.",
            detail="A batch needs at least one chunk with a question count above zero.",
        )

    planned: list[PlannedQuestion] = []
    for chunk in chunks:
        _reject_negative_counts(chunk)
        # Tested against the per-format total, not the multiplied one: a chunk with
        # counts but no format multiplies out to zero, and must report the missing
        # format rather than being skipped as if it asked for nothing.
        if chunk.per_format_total == 0:
            continue
        if not chunk.question_types:
            raise InvalidQuestionSpecError(
                "Every chunk that asks for questions must name at least one format.",
                detail=f"Section {chunk.section_id} has a question count but no question type.",
            )

        for difficulty in DIFFICULTY_ORDER:
            for _ in range(chunk.counts.get(difficulty, 0)):
                for question_type in chunk.question_types:
                    planned.append(
                        PlannedQuestion(
                            section_id=chunk.section_id,
                            difficulty=difficulty,
                            question_type=question_type,
                        )
                    )

    if not planned:
        raise InvalidQuestionSpecError(
            "Nothing was asked for.",
            detail="Every selected chunk asks for zero questions.",
        )
    return planned


def count_identical_requests(planned: Sequence[PlannedQuestion]) -> int:
    """How many planned questions repeat a (section, difficulty, format) already planned.

    A count above one at a single difficulty produces exactly this: two medium
    questions in one format are two identical requests. It is not refused — a
    professor may legitimately want two questions on one chunk at one difficulty —
    but nothing currently makes the second differ from the first, because
    ``QuestionSpec.seed`` is carried and never reaches the prompt. The console
    shows this number so that asking for near-duplicates is a decision rather than
    a surprise.
    """
    seen = Counter(
        (question.section_id, question.difficulty, question.question_type) for question in planned
    )
    return sum(count - 1 for count in seen.values() if count > 1)
