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


def needed_for(count: int, *, minimum: int = MIN_QUESTIONS_PER_CELL) -> int:
    """How many more questions this cell needs before it stops repeating.

    An upper bound on the *work*, not on the questions: one question may claim
    three subtopics, so a single generation can close this cell in three rows at
    once. Summing these across a topic therefore overstates how many questions
    must be written, which is why the page counts gaps and hedges the questions.
    """
    return max(0, minimum - count)


class CoverageCell(BaseModel):
    """One (subtopic, difficulty) pair and how many questions cover it."""

    difficulty: Difficulty
    count: int
    state: CoverageState
    #: Questions still owed to this cell. Zero once it is ready.
    needed: int = 0


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

    @property
    def gap_count(self) -> int:
        """Cells in this row still owed questions, empty and thin alike."""
        return sum(1 for cell in self.cells if cell.needed > 0)

    @property
    def questions_needed(self) -> int:
        return sum(cell.needed for cell in self.cells)


class TopicCoverage(BaseModel):
    """One topic's rows, and what a professor would have to do about it.

    The grouping the coverage page is read through. A professor decides what to
    write next a topic at a time -- a chunk teaches one topic, so a gap in
    another topic is not work they can act on in the same breath.
    """

    topic_id: int
    topic_name: str
    #: Distinct approved questions claiming this topic. Lower than the sum of
    #: the cells, because one question may claim three of its subtopics.
    approved_questions: int = 0
    subtopics: list[SubtopicCoverage] = Field(default_factory=list)

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
    def ready_cells(self) -> int:
        return self.total_cells - self.empty_cells - self.thin_cells

    @property
    def gap_count(self) -> int:
        return sum(row.gap_count for row in self.subtopics)

    @property
    def questions_needed(self) -> int:
        return sum(row.questions_needed for row in self.subtopics)

    @property
    def is_complete(self) -> bool:
        """Every cell at or above the target, so there is nothing to do here."""
        return self.total_cells > 0 and self.gap_count == 0


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
    topics: list[TopicCoverage] = Field(default_factory=list)
    #: Distinct approved questions behind the grid. Lower than the sum of the
    #: cells whenever a question claims more than one subtopic.
    question_count: int = 0

    @property
    def subtopics(self) -> list[SubtopicCoverage]:
        """Every row, flat, in taxonomy order.

        Derived from :attr:`topics` rather than stored beside it. Two lists of
        the same rows would eventually disagree, and the one that disagreed
        would be whichever the professor happened to be reading.
        """
        return [row for topic in self.topics for row in topic.subtopics]

    @property
    def incomplete_topics(self) -> list[TopicCoverage]:
        return [topic for topic in self.topics if not topic.is_complete]

    @property
    def complete_topics(self) -> list[TopicCoverage]:
        return [topic for topic in self.topics if topic.is_complete]

    @property
    def gap_count(self) -> int:
        return sum(topic.gap_count for topic in self.topics)

    @property
    def questions_needed(self) -> int:
        return sum(topic.questions_needed for topic in self.topics)

    @property
    def ready_cells(self) -> int:
        return self.total_cells - self.empty_cells - self.thin_cells

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
