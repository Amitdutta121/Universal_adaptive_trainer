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
from typing import Annotated, Any, Literal, ParamSpec, TypeVar

from pydantic import BaseModel, Field, TypeAdapter
from pydantic_ai import FunctionToolset, RunContext
from sqlalchemy.orm import Session

from app.agent.approvals import APPROVAL_REQUIRED, PlannedRun, open_plan, store_plan
from app.curriculum import TaxonomyImportService, TreeUpdate
from app.curriculum.drafting import DraftBrief, draft_taxonomy
from app.curriculum.taxonomy_schema import TaxonomyDocument
from app.domain.enums import GuidanceLevel
from app.errors import AdaptiveTrainerError, DomainRuleError, NotFoundError
from app.generation.rounds import plan_targets
from app.ingestion.youtube import AvailabilityCheck, TranscriptFetch
from app.jobs.queue import JobQueue
from app.llm.client import StructuredLLMClient
from app.persistence.models import QuestionSetupRow
from app.persistence.repositories import CurriculumRepository
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever
from app.retrieval.embedder import Embedder
from app.styles.schema import SetupSuggestion
from app.subjects import profile_for_course_id
from app.tutorials import experimental
from app.web.routes.api import books as books_routes
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
    question_in_course,
    subtopics_in_course,
    version_in_course,
)
from app.web.routes.api.retrieval import get_query_embedder
from app.web.routes.api.schemas import (
    ChunksRunTarget,
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

    books: list[dict[str, Any]]
    curriculum_versions: list[dict[str, Any]]
    approved_curriculum_version_id: int | None


@tool
def course_overview(ctx: RunContext[AgentDeps]) -> CourseOverview:
    """The course's imported material and curriculum versions, with their ids."""
    deps = ctx.deps
    with deps.session_factory() as session:
        books = books_routes.list_books(session, deps.course_id)
        versions = curriculum_routes.list_versions(session, deps.course_id)
    return CourseOverview(
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
                    include={"id", "name", "summary", "question_type", "difficulty_range"},
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


# -- Navigation -------------------------------------------------------------------------------

#: Each Studio view's path inside ``/courses/{course}``; ``{id}`` is ``open_view``'s ``id``.
VIEW_PATHS: dict[str, str] = {
    "dashboard": "/dashboard",
    "library": "/books",
    "book": "/books/{id}",
    "curriculum": "/curriculum",
    "curriculum_version": "/curriculum/versions/{id}",
    "subtopic": "/curriculum/subtopics/{id}",
    "questions": "/questions",
    "question": "/questions/{id}",
    "generate": "/questions/generate",
    "review": "/review",
    "coverage": "/coverage",
    "students": "/students",
    "tutorials": "/tutorials",
    "judges": "/judges",
}
View = Literal[
    "dashboard",
    "library",
    "book",
    "curriculum",
    "curriculum_version",
    "subtopic",
    "questions",
    "question",
    "generate",
    "review",
    "coverage",
    "students",
    "tutorials",
    "judges",
]


class OpenedView(BaseModel):
    """The Studio page the chat panel navigates to, inside the current course."""

    view: str
    path: str


@tool
def open_view(ctx: RunContext[AgentDeps], view: View, id: int | None = None) -> OpenedView:
    """Open a page of the Studio, only when the professor asks to see or go to one.

    Not a way to answer a question: read the answer with the matching tool and say it.
    ``book``, ``curriculum_version``, ``subtopic`` and ``question`` need that row's ``id``.
    """
    template = VIEW_PATHS[view]
    if "{id}" not in template:
        return OpenedView(view=view, path=template)
    if id is None:
        raise DomainRuleError(f"Opening the {view} page needs its id.")
    deps = ctx.deps
    with deps.session_factory() as session:
        if view == "book":
            book_in_course(session, id, deps.course_id)
        elif view == "curriculum_version":
            version_in_course(session, id, deps.course_id)
        elif view == "subtopic":
            CurriculumRepository(session).get_subtopic(id)
            subtopics_in_course(session, [id], deps.course_id)
        else:
            question_in_course(session, id, deps.course_id)
    return OpenedView(view=view, path=template.format(id=id))
