"""The agent's tools. Each one is a thin call into the function a Studio route already uses.

A tool opens its own session per call (the agent's run outlives the request's session) and
passes the request's course, so course scoping is the route function's own check. A refusal
the app raises (:class:`~app.errors.AdaptiveTrainerError`) is returned to the model as a
:class:`ToolRefusal` it can explain, never swallowed and never retried as if it were a bug.
"""

from __future__ import annotations

import functools
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, ParamSpec, TypeVar

from pydantic import BaseModel, Field, TypeAdapter
from pydantic_ai import FunctionToolset, RunContext
from sqlalchemy.orm import Session

from app import course_design
from app.agent.approvals import APPROVAL_REQUIRED, PlannedRun, open_plan, store_plan
from app.assessment import catalog
from app.course_design.approve import ApprovedDesign, approve_design
from app.curriculum import TaxonomyImportService, TreeUpdate
from app.curriculum.capabilities import capabilities_text
from app.curriculum.drafting import DraftBrief, draft_taxonomy
from app.curriculum.taxonomy_schema import TaxonomyDocument
from app.domain.enums import GuidanceLevel
from app.errors import AdaptiveTrainerError, DomainRuleError, NotFoundError
from app.generation.rounds import plan_targets
from app.ingestion.youtube import AvailabilityCheck, TranscriptFetch
from app.jobs.queue import JobQueue
from app.llm.client import StructuredLLMClient, get_structured_client
from app.persistence.models import BookRow, CourseRow, QuestionSetupRow
from app.persistence.repositories import ChunkRepository, CurriculumRepository
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever
from app.retrieval.embedder import Embedder
from app.styles import drafting as style_drafting
from app.styles.library import get_library
from app.styles.schema import SetupSuggestion
from app.subjects import profile_for_course_id
from app.tutorials import experimental
from app.web.routes.api import books as books_routes
from app.web.routes.api import courses as course_routes
from app.web.routes.api import coverage as coverage_routes
from app.web.routes.api import curriculum as curriculum_routes
from app.web.routes.api import generation_runs as run_routes
from app.web.routes.api import questions as question_routes
from app.web.routes.api import setup as setup_routes
from app.web.routes.api import students as student_routes
from app.web.routes.api import tutorials as tutorial_routes
from app.web.routes.api.deps import (
    book_in_course,
    ensure_in_course,
    subtopics_in_course,
)
from app.web.routes.api.retrieval import get_query_embedder
from app.web.routes.api.schemas import (
    ChunksRunTarget,
    CourseUpdate,
    CreateCourseStyleRequest,
    CurriculumVersionDetail,
    GapsRunTarget,
    GenerationRunPlan,
    RegenerateRunTarget,
    RunTarget,
    SaveSetupRequest,
    SetupCellsRunTarget,
    SuggestSetupRequest,
    TutorialRecipeDecisionOut,
    TutorialRecipeDecisionRequest,
    YouTubeImportRequest,
)


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
    generation_client: StructuredLLMClient | None = None
    setup_client: StructuredLLMClient | None = None
    youtube_fetch: TranscriptFetch | None = None
    youtube_check: AvailabilityCheck | None = None
    #: Writes tutorial recipes and blocks (the ``tutorials`` model role). Built only when a
    #: recipe tool runs, so an unconfigured role never breaks the chat; tests pass a fake.
    tutorial_client: StructuredLLMClient | None = None
    embedder: Callable[[], Embedder] = get_query_embedder


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
    """Register ``func`` on :data:`toolset`, with app refusals returned to the model.

    A tool named in :data:`~app.agent.approvals.APPROVAL_REQUIRED` runs only after the
    professor approves that call in the chat (see :mod:`app.agent.approvals`).
    """
    toolset.tool(_refusals_to_model(func), requires_approval=func.__name__ in APPROVAL_REQUIRED)
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

    Book files (PDF, DOCX, PPTX) are attached in the chat instead, which imports them. If the
    transcript cannot be fetched, ask the professor to paste it and call again with
    ``transcript``.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        result = books_routes.import_youtube(
            session,
            deps.course_id,
            YouTubeImportRequest(url=url, title=title, transcript=transcript),
            deps.youtube_fetch or books_routes.get_youtube_fetch(),
            deps.youtube_check or books_routes.get_youtube_check(),
            queue=deps.queue,
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
    #: Parts of the course the app cannot teach or check: tell the professor about them.
    out_of_scope: list[str]


@tool
def propose_curriculum(ctx: RunContext[AgentDeps], brief: DraftBrief) -> CurriculumProposal:
    """Draft a Topic -> Subtopic taxonomy from the professor's description. Saves nothing."""
    draft = draft_taxonomy(brief, client=ctx.deps.draft_client)
    return CurriculumProposal(
        document=draft.document.model_dump(),
        analysis=draft.analysis,
        drafted_by=draft.drafted_by,
        out_of_scope=draft.out_of_scope,
    )


# -- Course design: the curriculum with how each subtopic is taught and checked (ADR-078) ------


class DesignStyleView(BaseModel):
    name: str
    #: The question type as the professor sees it.
    question_type: str
    summary: str
    #: The figure each question shows the student, as the professor sees it; ``None`` for none.
    figure: str | None = None
    #: True when it would be drafted on approval; false when the course already has it.
    new: bool
    #: A reused style's own name, when it was written for another course.
    reused_from: str | None = None
    used_by: int


class DesignRecipeView(BaseModel):
    name: str
    #: The tutorial form as the professor sees it.
    form: str
    summary: str
    new: bool
    reused_from: str | None = None
    used_by: int


class DesignSubtopicView(BaseModel):
    name: str
    description: str
    styles: list[str]
    recipes: list[str]


class DesignTopicView(BaseModel):
    name: str
    subtopics: list[DesignSubtopicView]


class CourseDesignView(BaseModel):
    """A course design as it stands, in the professor's terms. Nothing is saved."""

    #: Pass to the next step: suggest_styles, suggest_recipes, show_design, a revision, approval.
    design_id: str
    title: str
    audience: str
    topic_count: int
    subtopic_count: int
    #: False until suggest_styles has run for the current curriculum.
    styles_ready: bool
    #: False until suggest_recipes has run for the current curriculum.
    recipes_ready: bool
    styles: list[DesignStyleView]
    recipes: list[DesignRecipeView]
    topics: list[DesignTopicView]
    #: Syllabus parts left outside the app: always tell the professor.
    out_of_scope: list[str]


_FORM_LABELS = {
    "markdown": "Written explanation",
    "mermaid": "Diagram",
    "chartjs": "Chart",
    "html": "Interactive page",
    "video_clip": "Lecture clip",
}


def _figure_label(kind: str) -> str | None:
    figure = catalog.FIGURE_KINDS_BY_ID.get(kind)
    return figure.label if figure is not None else None


def design_view(design) -> CourseDesignView:
    """What the chat shows of a ``CourseDesign``: names, never keys or ids."""
    style_names = {s.key: s.name for s in design.styles}
    recipe_names = {r.key: r.name for r in design.recipes}
    style_keys = design.style_use or {}
    recipe_keys = design.recipe_use or {}
    style_use = Counter(k for ks in style_keys.values() for k in ks)
    recipe_use = Counter(k for ks in recipe_keys.values() for k in ks)
    topics = []
    for t, topic in enumerate(design.curriculum.topics, start=1):
        subtopics = []
        for n, sub in enumerate(topic.subtopics, start=1):
            key = f"T{t}.S{n}"
            subtopics.append(
                DesignSubtopicView(
                    name=sub.name,
                    description=sub.description or "",
                    styles=[style_names[k] for k in style_keys.get(key, [])],
                    recipes=[recipe_names[k] for k in recipe_keys.get(key, [])],
                )
            )
        topics.append(DesignTopicView(name=topic.name, subtopics=subtopics))
    return CourseDesignView(
        design_id=design.id,
        title=design.curriculum.label,
        audience=design.brief.audience,
        topic_count=len(topics),
        subtopic_count=sum(len(t.subtopics) for t in topics),
        styles_ready=design.style_use is not None,
        recipes_ready=design.recipe_use is not None,
        styles=[
            DesignStyleView(
                name=s.name,
                question_type=catalog.TYPES_BY_ID[s.question_type].label,
                summary=s.summary,
                figure=_figure_label(s.figure),
                new=s.existing_id is None,
                reused_from=s.original_name,
                used_by=style_use[s.key],
            )
            for s in design.styles
        ],
        recipes=[
            DesignRecipeView(
                name=r.name,
                form=_FORM_LABELS.get(r.form, r.form),
                summary=r.summary,
                new=r.existing_id is None,
                reused_from=r.original_name,
                used_by=recipe_use[r.key],
            )
            for r in design.recipes
        ],
        topics=topics,
        out_of_scope=design.out_of_scope,
    )


def _catalogue(deps: AgentDeps) -> course_design.DesignCatalogue:
    with deps.session_factory() as session:
        return course_design.design_catalogue(
            session, profile_for_course_id(session, deps.course_id)
        )


@tool
def design_curriculum(
    ctx: RunContext[AgentDeps],
    brief: DraftBrief | None = None,
    design_id: str = "",
    change: str = "",
) -> CourseDesignView:
    """Start a course design with its curriculum, or redraft a design's curriculum. Saves nothing.

    For a new design pass ``brief``, filled from the material; the result's ``design_id`` is
    what the other design tools take. To change topics or subtopics, pass ``design_id`` and the
    professor's ``change``: the styles and recipes then need suggesting again. One model call.
    """
    deps = ctx.deps
    design = course_design.get_design(design_id, deps.course_id) if design_id else None
    return design_view(
        course_design.design_curriculum(
            course_id=deps.course_id,
            brief=brief,
            design=design,
            change=change,
            draft_client=deps.draft_client,
        )
    )


@tool
def suggest_styles(
    ctx: RunContext[AgentDeps], design_id: str, change: str = ""
) -> CourseDesignView:
    """Suggest the design's question styles: how each subtopic is checked. Saves nothing.

    Picks as few styles as the curriculum needs, reusing the course's own where they fit, and
    which ones each subtopic uses. Pass the professor's ``change`` to revise them; the rest of
    the design is kept. One model call; can run alongside suggest_recipes.
    """
    deps = ctx.deps
    design = course_design.get_design(design_id, deps.course_id)
    return design_view(
        course_design.suggest_styles(
            design, _catalogue(deps), change=change, client=deps.setup_client
        )
    )


@tool
def suggest_recipes(
    ctx: RunContext[AgentDeps], design_id: str, change: str = ""
) -> CourseDesignView:
    """Suggest the design's tutorial recipes: how each subtopic is taught. Saves nothing.

    Picks as few recipes as the curriculum needs, reusing the course's own where they fit, and
    which ones each subtopic uses. Pass the professor's ``change`` to revise them; the rest of
    the design is kept. One model call; can run alongside suggest_styles.
    """
    deps = ctx.deps
    design = course_design.get_design(design_id, deps.course_id)
    return design_view(
        course_design.suggest_recipes(
            design, _catalogue(deps), change=change, client=deps.setup_client
        )
    )


@tool
def show_design(ctx: RunContext[AgentDeps], design_id: str) -> CourseDesignView:
    """Show the professor the design as it stands, as a card they review and change in place.

    Call it once the steps you ran are done, instead of describing the design in text. No model
    call.
    """
    return design_view(course_design.get_design(design_id, ctx.deps.course_id))


@tool
def approve_course_design(ctx: RunContext[AgentDeps], design_id: str) -> ApprovedDesign:
    """Save a proposed course design as the professor approved it. Waits for approval.

    Saves the curriculum, drafts and saves each new tutorial recipe, and approves the design's
    recipes for the curriculum. Drafts each new question style without saving it (one model
    call each): offer every ``style_drafts`` entry with ``save_style``. Returns every
    subtopic's saved and pending style ids for planning generation.
    """
    deps = ctx.deps
    return approve_design(
        course_design.get_design(design_id, deps.course_id),
        session_factory=deps.session_factory,
        style_client=deps.setup_client or get_structured_client(),
        recipe_client=_tutorial_client(deps),
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


# -- Approval-gated: curriculum, styles, publishing -------------------------------------------


@tool
def approve_curriculum(ctx: RunContext[AgentDeps], document: TaxonomyDocument) -> CurriculumTree:
    """Save a proposed taxonomy as the course's approved curriculum. Waits for approval.

    ``document`` is a proposal's ``document`` (as edited with the professor), unchanged in shape.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        version = TaxonomyImportService(session).import_upload(
            filename="taxonomy.json",
            data=document.model_dump_json().encode("utf-8"),
            course_id=deps.course_id,
        )
        session.commit()
        return CurriculumTree.from_detail(
            curriculum_routes.get_version(session, deps.course_id, version.id)
        )


class MaterialText(BaseModel):
    """A stretch of one imported book's text, in reading order."""

    book_id: int
    title: str
    #: Text of the chunks from ``start`` on, each under its section heading, up to the limit.
    text: str
    #: Pass as ``start`` to read on; ``None`` when this reached the end.
    next_start: int | None
    total_chunks: int


#: The most text one ``read_material`` call returns; read on with ``next_start``.
MATERIAL_CHARS = 24_000


@tool
def read_material(ctx: RunContext[AgentDeps], book_id: int, start: int = 0) -> MaterialText:
    """Read an imported book, syllabus or slide deck: its text in reading order.

    Ids come from ``course_overview``. A file attached a moment ago is listed there only once
    its import has finished. Long material comes in parts: call again with ``next_start``.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        book_in_course(session, book_id, deps.course_id)
        book = session.get(BookRow, book_id)
        chunks = ChunkRepository(session).list_for_book(book_id)
        parts: list[str] = []
        used = 0
        index = start
        last_heading: tuple[str, ...] = ()
        while index < len(chunks) and (used < MATERIAL_CHARS or not parts):
            chunk = chunks[index]
            heading = tuple(chunk.heading_path or ())
            piece = chunk.text
            if heading and heading != last_heading:
                piece = f"## {' > '.join(heading)}\n{piece}"
                last_heading = heading
            parts.append(piece)
            used += len(piece)
            index += 1
        return MaterialText(
            book_id=book_id,
            title=book.title if book else "",
            text="\n\n".join(parts),
            next_start=index if index < len(chunks) else None,
            total_chunks=len(chunks),
        )


class AppCapabilities(BaseModel):
    """The boundary of what can be made for any course (ADR-077)."""

    text: str


@tool
def app_capabilities(ctx: RunContext[AgentDeps]) -> AppCapabilities:
    """What tutorial recipes and question styles are built from, and what no course can do.

    Read it before drafting a curriculum, a style or a recipe, or judging which parts of a
    syllabus the app can take on. No model call.
    """
    return AppCapabilities(text=capabilities_text())


# -- The course itself: subject and question types ---------------------------------------------


class SubjectOptions(BaseModel):
    """What ``set_course_subject`` accepts."""

    subjects: list[dict[str, Any]]
    #: The question types a course can use today (each must be built end to end).
    question_types: list[dict[str, Any]]


@tool
def subject_options(ctx: RunContext[AgentDeps]) -> SubjectOptions:
    """The subject presets and usable question types, for choosing the course's subject.

    ``has_library``: the subject ships curated question styles; without one, draft the
    course's own with ``draft_style``. Use ``custom`` when no preset fits.
    """
    return SubjectOptions(
        subjects=[
            {
                "id": preset.id,
                "label": preset.label,
                "description": preset.description,
                "default_types": catalog.default_types_for(preset.id),
                "has_library": bool(get_library(preset.id)),
            }
            for preset in catalog.SUBJECTS
        ],
        question_types=[
            {"id": spec.id, "label": spec.label}
            for spec in catalog.QUESTION_TYPES
            if catalog.is_offerable(spec.id)
        ],
    )


class CourseSettings(BaseModel):
    subject: str
    question_types: list[str]
    #: False when the course already had this subject and these types: nothing was asked.
    changed: bool = True


@tool
def set_course_subject(
    ctx: RunContext[AgentDeps], subject: str, question_types: list[str] | None = None
) -> CourseSettings:
    """Set the course's subject and, optionally, its question types, as detected from the
    material. Runs at once, with no approval card: the professor corrects it in the chat.
    Asking for what the course already has changes nothing and returns ``changed`` false.

    Only before the course has questions or styles of its own. Without ``question_types``
    the course takes the subject's default types. Ids come from ``subject_options``.
    """
    deps = ctx.deps
    if deps.course_id is None:
        raise DomainRuleError("Open a course first.")
    with deps.session_factory() as session:
        course = session.get(CourseRow, deps.course_id)
        if course is None:
            raise NotFoundError("Course not found.")
        wanted = (
            question_types if question_types is not None else catalog.default_types_for(subject)
        )
        if course.subject == subject and set(course.question_types) == set(wanted):
            return CourseSettings(
                subject=subject, question_types=list(course.question_types), changed=False
            )
    with deps.session_factory() as session:
        course = course_routes.change_course(
            session,
            deps.user_id,
            deps.course_id,
            CourseUpdate(subject=subject, question_types=question_types),
        )
    return CourseSettings(
        subject=course.subject or catalog.LEGACY_SUBJECT,
        question_types=list(course.question_types),
    )


class StyleDraftOut(BaseModel):
    """A style in the library's YAML format, ready for ``save_style``. Never saved."""

    yaml: str
    #: Empty when the draft passes the style checks; otherwise why not, after one repair.
    problems: list[str]
    #: The style's fields, which the chat shows as a card.
    style: dict[str, Any] | None = None


@tool
def draft_style(
    ctx: RunContext[AgentDeps], description: str, current_yaml: str = ""
) -> StyleDraftOut:
    """Draft a question style from the professor's words, or revise ``current_yaml``.

    One model call. The draft is checked like a saved style: its two examples go through
    their question type's checks and grader. Saves nothing; show it, then ``save_style``.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        result = style_drafting.draft_style(
            session,
            profile_for_course_id(session, deps.course_id),
            deps.setup_client or get_structured_client(),
            description,
            current_yaml or None,
        )
    return StyleDraftOut(
        yaml=result.yaml,
        problems=result.problems,
        style=result.style.model_dump(mode="json", exclude={"subject"}) if result.style else None,
    )


class SavedStyle(BaseModel):
    style_id: str
    name: str


@tool
def save_style(ctx: RunContext[AgentDeps], yaml: str) -> SavedStyle:
    """Add a question style to this course, in the library's YAML format. Waits for approval.

    The style must pass the same checks as a library file (CONTRIBUTING-styles.md).
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        style = setup_routes.create_course_style(
            session,
            profile_for_course_id(session, deps.course_id),
            CreateCourseStyleRequest(yaml=yaml),
        )
    return SavedStyle(style_id=style.id, name=style.name)


class PublishedSet(BaseModel):
    set_version_id: int
    label: str
    question_count: int
    #: The classroom link students join with; it stays the same across publishes.
    join_path: str


@tool
def publish_set(ctx: RunContext[AgentDeps], curriculum_version_id: int) -> PublishedSet:
    """Freeze the taxonomy's approved questions and point its classroom link at them.

    Waits for approval. Students already in a run keep the set they started on.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        published = coverage_routes.sync_taxonomy_set(
            session, deps.course_id, curriculum_version_id
        )
    return PublishedSet(
        set_version_id=published.id,
        label=published.label,
        question_count=published.question_count,
        join_path=f"/students/join?taxonomy={curriculum_version_id}",
    )


# -- Spending: plan, then run the approved plan -----------------------------------------------


class NewSetupTarget(SaveSetupRequest):
    """Save a question setup (styles per subtopic, a target per cell) and run its first round."""

    kind: Literal["new_setup"] = "new_setup"


AgentRunTarget = Annotated[
    ChunksRunTarget | GapsRunTarget | SetupCellsRunTarget | RegenerateRunTarget | NewSetupTarget,
    Field(discriminator="kind"),
]
_RUN_TARGET: TypeAdapter[RunTarget] = TypeAdapter(RunTarget)


class PricedPlan(BaseModel):
    """A run's dry-run plan and the id ``run_generation`` needs to start exactly this run."""

    plan_id: str
    #: Generation calls plus judge calls on every question's first attempt; the number the
    #: professor approves. A round's judges run inside its retry loop and are not counted.
    model_calls: int
    plan: GenerationRunPlan


def _new_setup_plan(session: Session, course: int | None, target: NewSetupTarget):
    version = CurriculumRepository(session).get_with_tree(target.curriculum_version_id)
    ensure_in_course(version.course_id, course, f"Curriculum version {version.id}")
    setup_routes._validate(session, version, target)
    unsaved = QuestionSetupRow(
        curriculum_version_id=target.curriculum_version_id,
        approved_styles={
            str(entry.subtopic_id): list(dict.fromkeys(entry.style_ids))
            for entry in target.approved_styles
            if entry.style_ids
        },
        cell_targets=[cell.model_dump(mode="json") for cell in target.cell_targets],
    )
    return run_routes.round_plan(
        target.kind, plan_targets(session, unsaved, size=target.round_size)
    )


@tool
def plan_generation(ctx: RunContext[AgentDeps], target: AgentRunTarget) -> PricedPlan:
    """Price a generation run without running it: the questions it would create and its calls.

    Kinds: ``chunks`` (questions from book chunks), ``gaps`` (fill coverage gaps),
    ``setup_cells`` (the next round of a saved setup), ``regenerate`` (replace one question),
    ``new_setup`` (save styles per subtopic and run the first round). Show the professor the
    plan, then call ``run_generation`` with its ``plan_id`` and ``model_calls``.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        if isinstance(target, NewSetupTarget):
            plan = _new_setup_plan(session, deps.course_id, target)
        else:
            plan = run_routes.plan_run(session, deps.course_id, target)
    calls = plan.totals.generation_calls + (plan.totals.judge_calls or 0)
    planned = PlannedRun(
        course_id=deps.course_id, target=target.model_dump(mode="json"), model_calls=calls
    )
    return PricedPlan(plan_id=store_plan(planned), model_calls=calls, plan=plan)


class StartedRun(BaseModel):
    kind: str
    #: ``job-N`` or ``round-N``, as the Jobs panel lists it.
    job_id: str


@tool
def run_generation(ctx: RunContext[AgentDeps], plan_id: str, model_calls: int) -> StartedRun:
    """Start a run priced by ``plan_generation``. Waits for approval; spends model credit.

    ``model_calls`` must be the plan's, so the professor approves the number it was priced at.
    """
    deps = ctx.deps
    plan = open_plan(plan_id, course_id=deps.course_id, model_calls=model_calls)
    with deps.session_factory() as session:
        if plan.target.get("kind") == "new_setup":
            saved = setup_routes.save_setup(
                session, deps.course_id, NewSetupTarget.model_validate(plan.target), deps.queue
            )
            return StartedRun(kind="new_setup", job_id=f"round-{saved.round_id}")
        started = run_routes.queue_run(
            session,
            deps.course_id,
            _RUN_TARGET.validate_python(plan.target),
            queue=deps.queue,
            client=deps.generation_client,
            embedder=deps.embedder,
        )
    return StartedRun(kind=started.kind, job_id=started.job_id)


# -- Reading the course: overview, styles, review, students -----------------------------------


class CourseOverview(BaseModel):
    """The ids the other tools take: the course's material and curriculum versions."""

    name: str
    #: Subject preset id (``intro_python``, ``custom``, ...); see ``subject_options``.
    subject: str
    #: What the professor calls it. ``custom`` means no preset: the course's own styles and
    #: recipes carry the subject, and the prompts are named after the course.
    subject_name: str
    #: ``{"id", "label"}``: say the label, pass the id.
    question_types: list[dict[str, str]]
    #: Styles the course can use: its subject's library plus the ones made for it.
    style_count: int
    books: list[dict[str, Any]]
    curriculum_versions: list[dict[str, Any]]
    approved_curriculum_version_id: int | None


@tool
def course_overview(ctx: RunContext[AgentDeps]) -> CourseOverview:
    """The course's subject, question types, imported material and curriculum versions."""
    deps = ctx.deps
    with deps.session_factory() as session:
        # The route already checked the professor may open this course (``X-Course-Id``).
        course = session.get(CourseRow, deps.course_id) if deps.course_id is not None else None
        profile = profile_for_course_id(session, deps.course_id)
        style_count = len(setup_routes.list_styles(session, profile).styles)
        books = books_routes.list_books(session, deps.course_id)
        versions = curriculum_routes.list_versions(session, deps.course_id)
    return CourseOverview(
        name=course.name if course else "",
        subject=profile.subject_id,
        subject_name=(
            "Not set (custom: the course's own styles and recipes)"
            if profile.subject_id == "custom"
            else catalog.SUBJECTS_BY_ID[profile.subject_id].label
        ),
        question_types=[
            {"id": type_id, "label": catalog.TYPES_BY_ID[type_id].label}
            for type_id in profile.question_types
            if type_id in catalog.TYPES_BY_ID
        ],
        style_count=style_count,
        books=[
            {"id": b.id, "title": b.title, "status": str(b.status), "format": str(b.source_format)}
            for b in books.books
        ],
        curriculum_versions=[
            {"id": v.id, "label": v.label, "status": str(v.status), "subtopics": v.subtopic_count}
            for v in versions.versions
        ],
        approved_curriculum_version_id=versions.approved_version_id,
    )


class StylePreview(BaseModel):
    """Styles side by side, each with its worked examples; or the catalogue to pick from."""

    styles: list[dict[str, Any]]


@tool
def preview_styles(
    ctx: RunContext[AgentDeps],
    style_ids: Annotated[list[str], Field(max_length=3)] | None = None,
) -> StylePreview:
    """Compare up to three question styles side by side, with their sample questions.

    With no ``style_ids``, lists every style this course can use (id, name, what it checks).
    No model call: the samples are the styles' own worked examples.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        library = setup_routes.list_styles(
            session, profile_for_course_id(session, deps.course_id)
        ).styles
    if not style_ids:
        return StylePreview(
            styles=[
                style.model_dump(
                    mode="json",
                    include={
                        "id",
                        "name",
                        "summary",
                        "question_type",
                        "difficulty_range",
                        "figure",
                    },
                )
                for style in library
            ]
        )
    by_id = {style.id: style for style in library}
    if unknown := [style_id for style_id in style_ids if style_id not in by_id]:
        raise NotFoundError(f"No style {', '.join(unknown)} in this course's library.")
    return StylePreview(styles=[by_id[style_id].model_dump(mode="json") for style_id in style_ids])


@tool
def suggest_setup(ctx: RunContext[AgentDeps], curriculum_version_id: int) -> SetupSuggestion:
    """Suggest styles per subtopic and a question target per cell, for a ``new_setup`` plan.

    One model call; saves nothing. Pass ``cell_targets`` to ``plan_generation`` unchanged.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        return setup_routes.suggest(
            session,
            deps.course_id,
            SuggestSetupRequest(curriculum_version_id=curriculum_version_id),
            deps.setup_client,
        )


class ReviewSummary(BaseModel):
    total: int
    reviewed: int
    remaining: int
    #: The next question waiting for a verdict, if any.
    next_question_id: int | None
    next_question_prompt: str | None


@tool
def review_summary(
    ctx: RunContext[AgentDeps], curriculum_version_id: int | None = None
) -> ReviewSummary:
    """How many generated questions still wait for the professor's review, and the next one."""
    deps = ctx.deps
    with deps.session_factory() as session:
        queue = question_routes.review_queue(
            session, deps.course_id, None, "all", curriculum_version_id
        )
    question = queue.question.question if queue.question else None
    return ReviewSummary(
        total=queue.total,
        reviewed=queue.reviewed,
        remaining=queue.remaining,
        next_question_id=question.id if question else None,
        next_question_prompt=question.prompt[:300] if question else None,
    )


#: How many weak subtopics a report lists.
WEAKEST = 5
#: How many students a class report lists, weakest first.
STUDENTS_LISTED = 50


class StudentLine(BaseModel):
    """One student, from this course's scored answers only."""

    student_id: int
    name: str
    answered: int
    #: 0 to 100; None before a first scored answer.
    average_score: float | None


class ClassReport(BaseModel):
    #: Students who have joined this course (or this taxonomy, when one was named).
    student_count: int
    #: Of those, students with at least one answer or mastery estimate.
    measured_students: int
    #: Average score of every scored answer, 0 to 100.
    average_score: float | None
    #: The subtopics the class is weakest in, weakest first.
    weakest_subtopics: list[dict[str, Any]]
    #: Every student (up to ``STUDENTS_LISTED``), lowest average first; ties go to the one with
    #: more answers, and students with no scored answer come last. An average over one or two
    #: answers says little: weigh ``answered`` before calling anyone weakest.
    students: list[StudentLine]


def _roster(
    session: Session, course: int | None, curriculum_version_id: int | None
) -> list[tuple[int, str]]:
    """(id, name) of every student on the course's roster, through the roster route."""
    found: list[tuple[int, str]] = []
    page = 1
    while True:
        listing = student_routes.list_students(
            session,
            course,
            search="",
            score="all",
            answered="all",
            activity="all",
            curriculum_version_id=curriculum_version_id,
            page=page,
            page_size=100,
            sort=None,
            order="asc",
        )
        found += [(row.id, row.display_name) for row in listing.students]
        if len(found) >= listing.total or not listing.students:
            return found
        page += 1


def _student_lines(
    roster: list[tuple[int, str]], scores: list[tuple[int, float]]
) -> list[StudentLine]:
    by_student: dict[int, list[float]] = {}
    for student_id, score in scores:
        by_student.setdefault(student_id, []).append(score)
    lines = [
        StudentLine(
            student_id=student_id,
            name=name,
            answered=len(by_student.get(student_id, [])),
            average_score=(
                round(sum(by_student[student_id]) / len(by_student[student_id]), 1)
                if by_student.get(student_id)
                else None
            ),
        )
        for student_id, name in roster
    ]
    return sorted(
        lines,
        key=lambda line: (
            line.average_score is None,
            line.average_score if line.average_score is not None else 0.0,
            -line.answered,
        ),
    )


class StudentReport(BaseModel):
    student_id: int
    name: str
    answered: int
    average_score: float | None
    topics: list[dict[str, Any]]
    #: The student's weakest subtopics, weakest first.
    weakest_subtopics: list[dict[str, Any]]


@tool
def student_report(
    ctx: RunContext[AgentDeps],
    student_id: int | None = None,
    curriculum_version_id: int | None = None,
) -> ClassReport | StudentReport:
    """Answer questions about students: how many there are, who they are, who is weakest or
    strongest (every student with their answers and average, lowest first), the class average
    and its weakest subtopics. With ``student_id`` (an id from this report): one student's
    answers, average, topic mastery and weak spots."""
    deps = ctx.deps
    with deps.session_factory() as session:
        if student_id is None:
            summary = student_routes.class_summary(session, deps.course_id, curriculum_version_id)
            lines = _student_lines(
                _roster(session, deps.course_id, curriculum_version_id),
                [(attempt.student_id, attempt.score) for attempt in summary.scored_attempts],
            )
            return ClassReport(
                students=lines[:STUDENTS_LISTED],
                student_count=summary.student_count,
                measured_students=summary.measured_students,
                average_score=summary.average_score,
                weakest_subtopics=[
                    {
                        "subtopic": cell.subtopic_name,
                        "topic": cell.topic_name,
                        "average_weakness": round(cell.average_weakness, 3),
                        "students": cell.student_count,
                    }
                    for cell in summary.weakness_cells[:WEAKEST]
                ],
            )
        progress = student_routes.student_progress(session, deps.course_id, student_id)
    weakest = sorted(progress.subtopics, key=lambda s: s.weakness, reverse=True)[:WEAKEST]
    return StudentReport(
        student_id=progress.student.id,
        name=progress.student.display_name,
        answered=progress.answered,
        average_score=progress.average_score,
        topics=[
            topic.model_dump(mode="json", include={"topic_name", "p_known", "band"})
            for topic in progress.topics
        ],
        weakest_subtopics=[
            s.model_dump(mode="json", include={"subtopic_name", "topic_name", "weakness"})
            for s in weakest
        ],
    )


# -- Tutorial recipes: list, draft, try, then save and approve ---------------------------------


def _tutorial_client(deps: AgentDeps) -> StructuredLLMClient:
    return deps.tutorial_client or tutorial_routes.get_tutorial_client()


class RecipeSummary(BaseModel):
    recipe_id: str
    name: str
    summary: str
    renderer: str
    guidance_levels: list[str]
    #: Made in the recipe builder for this course, rather than shipped with the subject.
    made_for_course: bool
    #: For this taxonomy: approved, rejected, or not decided yet.
    decision: Literal["approved", "rejected", "undecided"]


class RecipeList(BaseModel):
    #: With live tutorials, a library recipe is used until rejected; a course's own recipe only
    #: once approved. Without, only approved recipes reach students.
    live: bool
    recipes: list[RecipeSummary]


@tool
def list_recipes(ctx: RunContext[AgentDeps], curriculum_version_id: int) -> RecipeList:
    """The tutorial recipes students can get in this taxonomy, and each one's decision."""
    deps = ctx.deps
    with deps.session_factory() as session:
        listing = tutorial_routes.list_recipes(
            session,
            deps.course_id,
            profile_for_course_id(session, deps.course_id),
            curriculum_version_id,
        )
    decisions = listing.decisions or {}
    return RecipeList(
        live=listing.live,
        recipes=[
            RecipeSummary(
                recipe_id=recipe.id,
                name=recipe.name,
                summary=recipe.summary,
                renderer=recipe.renderer.value,
                guidance_levels=[level.value for level in recipe.guidance_levels],
                made_for_course=recipe.id.startswith(experimental.PREFIX),
                decision=(
                    "undecided"
                    if recipe.id not in decisions
                    else "approved"
                    if decisions[recipe.id]
                    else "rejected"
                ),
            )
            for recipe in listing.recipes
        ],
    )


class RecipeDraftOut(BaseModel):
    """A drafted recipe. Nothing is saved: show it, try it, then ``save_recipe`` it."""

    yaml: str
    #: Empty when the draft is valid; otherwise why it is not, after one repair.
    problems: list[str]


@tool
def draft_recipe(
    ctx: RunContext[AgentDeps], description: str, current_yaml: str = ""
) -> RecipeDraftOut:
    """Draft a tutorial recipe from the professor's words, or revise ``current_yaml`` with them.

    One model call on the tutorials model. Saves nothing.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        subject = profile_for_course_id(session, deps.course_id).storage_key
    result = experimental.draft_recipe(
        _tutorial_client(deps), subject, description, current_yaml or None
    )
    return RecipeDraftOut(yaml=result.yaml, problems=result.problems)


class TriedBlock(BaseModel):
    """One block the recipe wrote for a real subtopic, as a student would see it. Never saved."""

    renderer: str
    guidance_level: str
    payload: dict[str, Any]
    #: Why the block failed its checks, if it did.
    error: str | None


@tool
def try_recipe(
    ctx: RunContext[AgentDeps],
    yaml: str,
    subtopic_id: int,
    guidance_level: Literal["worked", "faded", "cue"] = "worked",
) -> TriedBlock:
    """Write one block of a recipe (saved or not) for a subtopic, to judge it. Saves nothing.

    One model call on the tutorials model, written and checked like any tutorial block.
    """
    deps = ctx.deps
    with deps.session_factory() as session:
        subtopics_in_course(session, [subtopic_id], deps.course_id)
        block = experimental.try_recipe(
            session,
            profile_for_course_id(session, deps.course_id),
            yaml,
            subtopic_id=subtopic_id,
            guidance_level=GuidanceLevel(guidance_level),
            client=_tutorial_client(deps),
            retriever=ChunkRetriever(session, ChunkEmbeddingStore(session, deps.embedder())),
        )
        # Chunks embedded on the way are worth keeping; the block never entered the session.
        session.commit()
    return TriedBlock(
        renderer=block.renderer.value,
        guidance_level=block.guidance_level.value,
        payload=block.payload,
        error=block.error,
    )


class SavedRecipe(BaseModel):
    recipe_id: str
    name: str
    #: Students get it only after ``decide_recipe`` approves it for a taxonomy.
    next_step: str = "Approve it for the taxonomy with decide_recipe before students see it."


@tool
def save_recipe(ctx: RunContext[AgentDeps], yaml: str) -> SavedRecipe:
    """Save a recipe to this course, or replace the saved one with the same id. Waits for
    approval. Replacing it hides the blocks written from its old wording."""
    deps = ctx.deps
    with deps.session_factory() as session:
        profile = profile_for_course_id(session, deps.course_id)
        recipe = experimental.parse_recipe(yaml, profile.storage_key)
        existing = next(
            (
                row
                for row in experimental.list_recipes(session, profile)
                if row.recipe_id == recipe.id
            ),
            None,
        )
        row = experimental.save_recipe(session, profile, yaml, existing.id if existing else None)
        session.commit()
        return SavedRecipe(recipe_id=row.recipe_id, name=recipe.name)


@tool
def decide_recipe(
    ctx: RunContext[AgentDeps], recipe_id: str, curriculum_version_id: int, approved: bool
) -> TutorialRecipeDecisionOut:
    """Approve a recipe for the taxonomy's students, or stop it (``approved`` false). Waits for
    approval. A recipe made for the course reaches students only once approved."""
    deps = ctx.deps
    with deps.session_factory() as session:
        return tutorial_routes.decide(
            session,
            deps.course_id,
            profile_for_course_id(session, deps.course_id),
            recipe_id,
            TutorialRecipeDecisionRequest(
                curriculum_version_id=curriculum_version_id, approved=approved
            ),
        )
