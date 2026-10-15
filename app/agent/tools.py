"""The agent's tools. Each one is a thin call into the function a Studio route already uses.

A tool opens its own session per call (the agent's run outlives the request's session) and
passes the request's course, so course scoping is the route function's own check. A refusal
the app raises (:class:`~app.errors.AdaptiveTrainerError`) is returned to the model as a
:class:`ToolRefusal` it can explain, never swallowed and never retried as if it were a bug.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

from pydantic import BaseModel
from pydantic_ai import FunctionToolset, RunContext
from sqlalchemy.orm import Session

from app.curriculum import TreeUpdate
from app.curriculum.drafting import DraftBrief, draft_taxonomy
from app.errors import AdaptiveTrainerError
from app.ingestion.youtube import AvailabilityCheck, TranscriptFetch
from app.jobs.queue import JobQueue
from app.llm.client import StructuredLLMClient
from app.web.routes.api import books as books_routes
from app.web.routes.api import coverage as coverage_routes
from app.web.routes.api import curriculum as curriculum_routes
from app.web.routes.api.schemas import CurriculumVersionDetail, YouTubeImportRequest


@dataclass
class AgentDeps:
    """What one chat run works with: the professor's course and the app's seams.

    ``draft_client``, ``youtube_fetch`` and ``youtube_check`` are the same dependencies the
    routes take, so a test override of the route dependency reaches the agent too.
    """

    session_factory: Callable[[], Session]
    course_id: int | None
    user_id: uuid.UUID
    queue: JobQueue
    draft_client: StructuredLLMClient | None = None
    youtube_fetch: TranscriptFetch | None = None
    youtube_check: AvailabilityCheck | None = None


class ToolRefusal(BaseModel):
    """The app refused the call; ``error`` is what the Studio would have shown."""

    error: str
    detail: str | None = None


P = ParamSpec("P")
R = TypeVar("R")


def _refusals_to_model(func: Callable[P, R]) -> Callable[P, R | ToolRefusal]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | ToolRefusal:
        try:
            return func(*args, **kwargs)
        except AdaptiveTrainerError as exc:
            return ToolRefusal(error=exc.message, detail=exc.detail)

    return wrapper


toolset: FunctionToolset[AgentDeps] = FunctionToolset()


def tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Register ``func`` on :data:`toolset`, with app refusals returned to the model."""
    toolset.tool(_refusals_to_model(func))
    return func


# -- Material ---------------------------------------------------------------------------------


class ImportedMaterial(BaseModel):
    book_id: int
    title: str
    status: str


@tool
def import_material(
    ctx: RunContext[AgentDeps], url: str, title: str = "", transcript: str = ""
) -> ImportedMaterial:
    """Import a YouTube video as course material, from its transcript.

    Book files (PDF, DOCX, PPTX) are uploaded in the Library's import dialog instead; open it
    with ``open_view``. If the transcript cannot be fetched, ask the professor to paste it and
    call again with ``transcript``.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        result = books_routes.import_youtube(
            session,
            deps.course_id,
            YouTubeImportRequest(url=url, title=title, transcript=transcript),
            deps.youtube_fetch or books_routes.get_youtube_fetch(),
            deps.youtube_check or books_routes.get_youtube_check(),
        )
    return ImportedMaterial(
        book_id=result.book.id, title=result.book.title, status=result.book.status.value
    )


# -- Curriculum -------------------------------------------------------------------------------


class CurriculumProposal(BaseModel):
    """A drafted taxonomy. Nothing is saved: it becomes a curriculum only when approved."""

    document: dict[str, Any]
    analysis: str
    drafted_by: str


@tool
def propose_curriculum(ctx: RunContext[AgentDeps], brief: DraftBrief) -> CurriculumProposal:
    """Draft a Topic -> Subtopic taxonomy from the professor's description. Saves nothing."""
    draft = draft_taxonomy(brief, client=ctx.deps.draft_client)
    return CurriculumProposal(
        document=draft.document.model_dump(), analysis=draft.analysis, drafted_by=draft.drafted_by
    )


class CurriculumTree(BaseModel):
    version_id: int
    label: str
    status: str
    topics: list[dict[str, Any]]

    @classmethod
    def from_detail(cls, detail: CurriculumVersionDetail) -> CurriculumTree:
        return cls(
            version_id=detail.version.id,
            label=detail.version.label,
            status=str(detail.version.status),
            topics=[
                {
                    "id": topic.id,
                    "name": topic.name,
                    "subtopics": [{"id": s.id, "name": s.name} for s in topic.subtopics],
                }
                for topic in detail.topics
            ],
        )


@tool
def edit_curriculum(
    ctx: RunContext[AgentDeps], version_id: int, update: TreeUpdate
) -> CurriculumTree:
    """Replace a saved curriculum version's tree: rename, add, reorder or hide rows.

    ``update`` is the whole tree as it should be; keep each existing row's ``id``. A row left
    out is hidden, not deleted. Editing the approved version changes what students see now.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        detail = curriculum_routes.update_tree(session, deps.course_id, version_id, update)
    return CurriculumTree.from_detail(detail)


# -- Coverage ---------------------------------------------------------------------------------


class CoverageGap(BaseModel):
    subtopic_id: int
    subtopic: str
    topic: str
    difficulty: str
    have: int
    needed: int


class CoverageSummary(BaseModel):
    curriculum_version_id: int | None
    curriculum_label: str | None
    question_count: int
    total_cells: int
    ready_cells: int
    questions_needed: int
    is_servable: bool
    is_ready: bool
    #: The cells still owed questions, emptiest first.
    gaps: list[CoverageGap]


@tool
def coverage_report(
    ctx: RunContext[AgentDeps], set_version_id: int | None = None
) -> CoverageSummary:
    """How well approved questions cover the approved curriculum, and which cells are short.

    Without ``set_version_id`` this is the live question bank; with one, that frozen set.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        report = coverage_routes.coverage(session, deps.course_id, set_version_id)
    gaps = [
        CoverageGap(
            subtopic_id=row.subtopic_id,
            subtopic=row.subtopic_name,
            topic=row.topic_name,
            difficulty=str(cell.difficulty),
            have=cell.count,
            needed=cell.needed,
        )
        for row in report.subtopics
        for cell in row.cells
        if cell.needed > 0
    ]
    gaps.sort(key=lambda gap: (gap.have, -gap.needed))
    return CoverageSummary(
        curriculum_version_id=report.curriculum_version_id,
        curriculum_label=report.curriculum_label,
        question_count=report.question_count,
        total_cells=report.total_cells,
        ready_cells=report.ready_cells,
        questions_needed=report.questions_needed,
        is_servable=report.is_servable,
        is_ready=report.is_ready,
        gaps=gaps,
    )
