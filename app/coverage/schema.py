"""The coverage grid, its three cell states, and the readiness verdict.

Pure. Nothing here touches the database; :mod:`app.coverage.service` supplies
the counts and this module decides what they mean.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.enums import Difficulty

#: Questions a (subtopic, difficulty) cell needs before it is usable.
#:
#: Not one. When the adaptive engine serves a question its priority drops to the
#: lowest, so the next request for the same cell prefers a different question --
#: and with a single question there is no different question to prefer. Three is
#: the smallest number that lets a student meet a cell twice without immediate
#: repetition; the professor can demand more, never fewer.
MIN_QUESTIONS_PER_CELL = 3


class CoverageState(StrEnum):
    """What one cell of the grid means for a training run."""

    #: No question at all. The engine can select this pair and find nothing.
    EMPTY = "empty"
    #: Fewer than :data:`MIN_QUESTIONS_PER_CELL`. Usable, but it repeats.
    THIN = "thin"
    #: Enough to rotate through.
    READY = "ready"


def state_for(count: int, *, minimum: int = MIN_QUESTIONS_PER_CELL) -> CoverageState:
    """Classify one cell's question count."""
    if count <= 0:
        return CoverageState.EMPTY
    if count < minimum:
        return CoverageState.THIN
    return CoverageState.READY


class CoverageCell(BaseModel):
    """One (subtopic, difficulty) pair and how many questions cover it."""

    difficulty: Difficulty
    count: int
    state: CoverageState


class SubtopicCoverage(BaseModel):
    """One subtopic's row of the grid, one cell per difficulty."""

    subtopic_id: int
    subtopic_name: str
    topic_id: int
    topic_name: str
    cells: list[CoverageCell] = Field(default_factory=list)

    @property
    def empty_count(self) -> int:
        return sum(1 for cell in self.cells if cell.state is CoverageState.EMPTY)

    @property
    def thin_count(self) -> int:
        return sum(1 for cell in self.cells if cell.state is CoverageState.THIN)

    @property
    def total_questions(self) -> int:
        """Question slots filled across this row.

        Not a count of distinct questions: one question tagged with two
        difficulties cannot exist, but one tagged with three subtopics appears
        in three rows. That is correct -- the engine would find it under each.
        """
        return sum(cell.count for cell in self.cells)


class CoverageReport(BaseModel):
    """The whole grid, plus the two counts a verdict rests on.

    ``empty_cells`` and ``thin_cells`` are kept apart because they are different
    failures. An empty cell is a request the engine cannot satisfy at all. A thin
    cell is satisfied, just repetitively. Collapsing both into one "not ready"
    would make a bank that needs one more question look like a bank that needs
    a hundred.
    """

    #: ``None`` when no curriculum is approved, which is its own kind of
    #: not-ready and is reported as such rather than as an empty grid.
    curriculum_version_id: int | None
    curriculum_label: str | None
    #: The frozen set this grid describes, or ``None`` for the live bank.
    set_version_id: int | None = None
    minimum_per_cell: int = MIN_QUESTIONS_PER_CELL
    subtopics: list[SubtopicCoverage] = Field(default_factory=list)
    #: Distinct approved questions behind the grid. Lower than the sum of the
    #: cells whenever a question claims more than one subtopic.
    question_count: int = 0

    @property
    def total_cells(self) -> int:
        return sum(len(row.cells) for row in self.subtopics)

    @property
    def empty_cells(self) -> int:
        return sum(row.empty_count for row in self.subtopics)

    @property
    def thin_cells(self) -> int:
        return sum(row.thin_count for row in self.subtopics)

    @property
    def is_servable(self) -> bool:
        """Whether the engine can satisfy every request this grid allows.

        False while any cell is empty. This is the blocking condition: a thin
        cell still returns a question.
        """
        return self.total_cells > 0 and self.empty_cells == 0

    @property
    def is_ready(self) -> bool:
        """Servable, and without a cell that would repeat immediately."""
        return self.is_servable and self.thin_cells == 0

    @property
    def gaps(self) -> list[tuple[SubtopicCoverage, CoverageCell]]:
        """Every empty cell, as the row and cell that need questions.

        Ordered as the taxonomy is, so the professor works down the curriculum
        rather than through a ranking the application invented.
        """
        return [
            (row, cell)
            for row in self.subtopics
            for cell in row.cells
            if cell.state is CoverageState.EMPTY
        ]
