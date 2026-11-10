"""A course design built step by step by the chat agent, and revised by chat (ADR-078).

A design is what a professor approves before anything is saved: the curriculum, a small set of
question styles (how students are checked) and tutorial recipes (how they are taught), and which
of those each subtopic uses. The chat agent is the planner. It reads the material, sets the
subject, and calls one tool per step, each a function here:

- :func:`design_curriculum` starts the design (or redrafts its curriculum), inside the app's
  boundary (:func:`app.curriculum.drafting.draft_taxonomy`);
- :func:`suggest_styles` and :func:`suggest_recipes` each plan their part for that curriculum:
  as few items as it needs, existing ones reused where they fit, new ones only where several
  subtopics need them, and which ones every subtopic uses. The agent runs them side by side.

Each plan is checked in code, not trusted: unknown ids are treated as new, a style must use a
question type the app can mark and a recipe a renderer it has, unused items are dropped, and
every subtopic ends with at least one style and one recipe. A reused item is shown under a name
in this course's terms, with the name it was written under kept beside it.

A design is kept (in this process, for a while) under one id that every step updates, so a
change re-runs only the step it is about. Nothing is written to the database.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.assessment import catalog
from app.curriculum.capabilities import capabilities_text
from app.curriculum.drafting import DraftBrief, draft_taxonomy
from app.curriculum.taxonomy_schema import TaxonomyDocument
from app.domain.enums import TutorialRenderer
from app.errors import DomainRuleError, NotFoundError
from app.llm.client import StructuredLLMClient, get_structured_client
from app.styles.library import styles_for
from app.subjects import SubjectProfile
from app.tutorials.generator import course_recipes

#: How long a proposed design can be revised or approved.
DESIGN_TTL_SECONDS = 4 * 60 * 60
#: Per subtopic, at most this many styles and recipes are kept from a plan.
MAX_STYLES_PER_SUBTOPIC = 3
MAX_RECIPES_PER_SUBTOPIC = 2

# -- What the plan may reuse ---------------------------------------------------------------------


@dataclass(frozen=True)
class ExistingItem:
    id: str
    name: str
    #: A question type id for a style, a renderer value for a recipe.
    kind: str
    summary: str
    #: A style's figure kind (``none`` when its questions carry no figure); unused for recipes.
    figure: str = "none"


@dataclass(frozen=True)
class DesignCatalogue:
    """The course's existing styles and recipes, read once before any model call."""

    styles: tuple[ExistingItem, ...] = ()
    recipes: tuple[ExistingItem, ...] = ()


def design_catalogue(session: Session, profile: SubjectProfile) -> DesignCatalogue:
    offerable = {spec.id for spec in catalog.QUESTION_TYPES if catalog.is_offerable(spec.id)}
    styles = tuple(
        ExistingItem(s.id, s.name, s.question_type.value, s.summary, s.figure)
        for s in styles_for(session, profile)
        if s.question_type.value in offerable
    )
    recipes = tuple(
        ExistingItem(r.id, r.name, r.renderer.value, r.summary)
        for r in course_recipes(session, profile.storage_key, profile.course_id)
    )
    return DesignCatalogue(styles=styles, recipes=recipes)


# -- The design ----------------------------------------------------------------------------------


class DesignStyle(BaseModel):
    key: str
    #: Set when an existing style is reused; ``None`` for one to draft on approval.
    existing_id: str | None = None
    #: The name in this course's terms.
    name: str
    #: The reused style's own name, when it was written for another course.
    original_name: str | None = None
    question_type: str
    #: What the student does and what it checks, in the course's terms. For a new style, the
    #: description it will be drafted from.
    summary: str
    #: The figure each question shows (``app.assessment.catalog.FIGURE_KINDS``), or ``none``.
    figure: str = "none"


class DesignRecipe(BaseModel):
    key: str
    existing_id: str | None = None
    name: str
    original_name: str | None = None
    #: A ``TutorialRenderer`` value.
    form: str
    summary: str


class CourseDesign(BaseModel):
    id: str
    course_id: int | None
    brief: DraftBrief
    curriculum: TaxonomyDocument
    out_of_scope: list[str] = Field(default_factory=list)
    styles: list[DesignStyle] = Field(default_factory=list)
    recipes: list[DesignRecipe] = Field(default_factory=list)
    #: ``"T<topic>.S<subtopic>"`` (1-based, in curriculum order) -> the style keys it uses;
    #: ``None`` until styles are suggested for the current curriculum.
    style_use: dict[str, list[str]] | None = None
    #: The same for recipe keys.
    recipe_use: dict[str, list[str]] | None = None


def subtopic_keys(curriculum: TaxonomyDocument) -> list[tuple[str, str, str]]:
    """``(key, topic name, subtopic name)`` for every subtopic, in order."""
    return [
        (f"T{t}.S{s}", topic.name, sub.name)
        for t, topic in enumerate(curriculum.topics, start=1)
        for s, sub in enumerate(topic.subtopics, start=1)
    ]


# -- The style and recipe planners ---------------------------------------------------------------


class _PlanStyle(BaseModel):
    key: str = Field(description="Short key you choose, e.g. s1; used in assignments.")
    existing_id: str | None = Field(
        default=None, description="An existing style's id when reusing it; null for a new one."
    )
    name: str = Field(
        description="Short name in this course's terms, as its instructor would say it, even "
        "for a reused style."
    )
    question_type: str = Field(description="One question type id from the list given.")
    summary: str = Field(description="One sentence: what the student does and what it checks.")
    figure: str = Field(
        default="none",
        description="none, or one figure kind id from the list given: the figure each "
        "question shows the student to read.",
    )


class _StyleAssignment(BaseModel):
    subtopic: str = Field(description="The subtopic key, e.g. T2.S1.")
    styles: list[str] = Field(description="1 to 3 style keys, most fitting first.")


class _StylePlan(BaseModel):
    reasoning: str = Field(
        description="Briefly, before the lists: the kinds of thinking the course asks of "
        "students, and which few styles check them."
    )
    styles: list[_PlanStyle]
    assignments: list[_StyleAssignment]


class _PlanRecipe(BaseModel):
    key: str = Field(description="Short key you choose, e.g. r1; used in assignments.")
    existing_id: str | None = None
    name: str = Field(description="Short name in this course's terms, even for a reused recipe.")
    form: str = Field(description="One tutorial form id from the list given.")
    summary: str = Field(description="One sentence: what the student sees.")


class _RecipeAssignment(BaseModel):
    subtopic: str = Field(description="The subtopic key, e.g. T2.S1.")
    recipes: list[str] = Field(description="1 or 2 recipe keys, most fitting first.")


class _RecipePlan(BaseModel):
    reasoning: str = Field(
        description="Briefly, before the lists: what students need to see to learn this "
        "course, and which few recipes show it."
    )
    recipes: list[_PlanRecipe]
    assignments: list[_RecipeAssignment]


_SHARED = """\
A generator later writes many questions per style and one tutorial block per recipe for every
subtopic that uses it, from the course's reading material.

Balance is the job:
- Use as few as the course needs; each one should serve several subtopics.
- Reuse an existing one whenever its own wording truly fits this course's subject; never reuse
  one written for a different subject. Give a reused one a name in this course's terms.
- Make a new one only when several subtopics need it, or one subtopic cannot be served
  otherwise. Write it in the course's own terms, not generic quiz wording.
- Stay inside the boundary you are given: only the ids listed.

"""

STYLE_SYSTEM = f"""\
You plan how a course's subtopics are checked in an adaptive training app. A question style is a
reusable way of asking about a subtopic, built on one question type.
{_SHARED}Size:
- A typical course needs about 3 to 7 styles, a small one fewer. Every subtopic gets 1 to
  3, together reaching from easy recall to harder reasoning where the subtopic allows: what a
  student of this subject does (trace, compute, choose, predict, spot the error).
Figures:
- Give a style a figure only when the subtopics it serves are about something to look at: a
  structure, a process or flow, states and transitions, a cycle, a dataset, a grid. The student
  then reads the figure to answer. Subtopics about definitions, facts or terms need none.
- Use only the figure kind ids given, and say in the summary what the figure shows.
"""

RECIPE_SYSTEM = f"""\
You plan how a course's subtopics are taught in an adaptive training app. A tutorial recipe is a
reusable way of teaching a subtopic, built on one tutorial form.
{_SHARED}Size:
- A typical course needs about 2 to 5 recipes. Every subtopic gets 1 or 2. Pick the form
  that shows the idea best: a diagram for a process or structure, an interactive page for something
  students should step through, a chart for numbers, a written explanation otherwise.
"""


def _curriculum_lines(curriculum: TaxonomyDocument) -> str:
    lines = []
    for t, topic in enumerate(curriculum.topics, start=1):
        lines.append(topic.name)
        for s, sub in enumerate(topic.subtopics, start=1):
            detail = f": {sub.description}" if sub.description else ""
            lines.append(f"  T{t}.S{s} {sub.name}{detail}")
    return "\n".join(lines)


def _existing(items: tuple[ExistingItem, ...]) -> str:
    return (
        "\n".join(
            f"- {i.id} ({i.kind}{'' if i.figure == 'none' else ', figure: ' + i.figure}): "
            f"{i.name}. {i.summary}"
            for i in items
        )
        or "(none)"
    )


def _plan_prompt(
    kind: Literal["styles", "recipes"],
    brief: DraftBrief,
    curriculum: TaxonomyDocument,
    catalogue: DesignCatalogue,
    previous: CourseDesign | None,
    change: str,
) -> str:
    parts = [
        capabilities_text(figures=kind == "styles"),
        f"# Course\n{brief.title}\n{brief.description}".strip(),
    ]
    if brief.audience.strip():
        parts.append(f"# Audience\n{brief.audience.strip()}")
    if kind == "styles":
        types = "\n".join(
            f"- {spec.id}: {spec.label} ({spec.widget})"
            for spec in catalog.QUESTION_TYPES
            if catalog.is_offerable(spec.id)
        )
        figures = "\n".join(
            f"- {figure.id}: {figure.label}" for figure in catalog.built_figure_kinds()
        )
        parts += [
            f"# Question type ids\n{types}",
            f"# Figure kind ids (or none)\n{figures}",
            f"# Existing styles (reuse by id when they fit)\n{_existing(catalogue.styles)}",
        ]
    else:
        forms = "\n".join(f"- {renderer.value}" for renderer in TutorialRenderer)
        parts += [
            f"# Tutorial form ids\n{forms}",
            f"# Existing recipes (reuse by id when they fit)\n{_existing(catalogue.recipes)}",
        ]
    parts.append(f"# Curriculum (subtopic keys)\n{_curriculum_lines(curriculum)}")
    if previous is not None:
        use = previous.style_use if kind == "styles" else previous.recipe_use
        current = {
            kind: [item.model_dump() for item in getattr(previous, kind)],
            "assignments": use or "(none: the curriculum changed; assign again)",
        }
        parts.append(
            f"# Current {kind}\nRevise them. Keep what the change does not touch, with the same "
            "keys and names. Subtopic keys may have moved if the curriculum changed; match by "
            f"name.\n{current}"
        )
        parts.append(f"# Change requested\n{change.strip() or 'Improve it.'}")
    return "\n\n".join(parts)


def _fill(chosen: dict[str, list[str]], keys: list[str]) -> dict[str, list[str]]:
    """Every subtopic with at least one item: one the plan left empty gets the most used."""
    use = Counter(k for ks in chosen.values() for k in ks)
    top = (use.most_common(1) or [(keys[0], 0)])[0][0]
    return {subtopic: ks or [top] for subtopic, ks in chosen.items()}


def _valid_styles(
    raw: _StylePlan, curriculum: TaxonomyDocument, catalogue: DesignCatalogue
) -> tuple[list[DesignStyle], dict[str, list[str]]]:
    offerable = {spec.id for spec in catalog.QUESTION_TYPES if catalog.is_offerable(spec.id)}
    existing = {item.id: item for item in catalogue.styles}
    styles: dict[str, DesignStyle] = {}
    for item in raw.styles:
        key = item.key.strip()
        if not key or key in styles:
            continue
        known = existing.get(item.existing_id or "")
        if known is not None:
            name = item.name.strip() or known.name
            styles[key] = DesignStyle(
                key=key, existing_id=known.id, name=name,
                original_name=known.name if name != known.name else None,
                question_type=known.kind, summary=item.summary.strip() or known.summary,
                figure=known.figure,
            )  # fmt: skip
        elif item.question_type in offerable and item.name.strip():
            styles[key] = DesignStyle(
                key=key, name=item.name.strip(), question_type=item.question_type,
                summary=item.summary.strip(), figure=_figure(item.figure),
            )  # fmt: skip
    if not styles:
        raise DomainRuleError("The plan had no usable question style. Ask for the design again.")
    given = {a.subtopic.strip(): a.styles for a in raw.assignments}
    chosen = {
        key: [k for k in dict.fromkeys(given.get(key, [])) if k in styles][:MAX_STYLES_PER_SUBTOPIC]
        for key, _topic, _name in subtopic_keys(curriculum)
    }
    chosen = _fill(chosen, list(styles))
    used = {k for ks in chosen.values() for k in ks}
    return [s for k, s in styles.items() if k in used], chosen


def _figure(raw: str) -> str:
    """A planned style's figure kind; ``none`` when it names no kind that can be made today."""
    kind = catalog.FIGURE_KINDS_BY_ID.get(raw.strip().lower())
    return kind.id if kind is not None and kind.built else "none"


def _valid_recipes(
    raw: _RecipePlan, curriculum: TaxonomyDocument, catalogue: DesignCatalogue
) -> tuple[list[DesignRecipe], dict[str, list[str]]]:
    forms = {renderer.value for renderer in TutorialRenderer}
    existing = {item.id: item for item in catalogue.recipes}
    recipes: dict[str, DesignRecipe] = {}
    for item in raw.recipes:
        key = item.key.strip()
        if not key or key in recipes:
            continue
        known = existing.get(item.existing_id or "")
        if known is not None:
            name = item.name.strip() or known.name
            recipes[key] = DesignRecipe(
                key=key, existing_id=known.id, name=name,
                original_name=known.name if name != known.name else None,
                form=known.kind, summary=item.summary.strip() or known.summary,
            )  # fmt: skip
        elif item.form in forms and item.name.strip():
            recipes[key] = DesignRecipe(
                key=key, name=item.name.strip(), form=item.form, summary=item.summary.strip()
            )
    if not recipes:
        raise DomainRuleError("The plan had no usable tutorial recipe. Ask for the design again.")
    given = {a.subtopic.strip(): a.recipes for a in raw.assignments}
    chosen = {
        key: [k for k in dict.fromkeys(given.get(key, [])) if k in recipes][
            :MAX_RECIPES_PER_SUBTOPIC
        ]
        for key, _topic, _name in subtopic_keys(curriculum)
    }
    chosen = _fill(chosen, list(recipes))
    used = {k for ks in chosen.values() for k in ks}
    return [r for k, r in recipes.items() if k in used], chosen


def _plan_styles(llm, brief, curriculum, catalogue, previous, change):
    raw = llm.complete_structured(
        system=STYLE_SYSTEM,
        prompt=_plan_prompt("styles", brief, curriculum, catalogue, previous, change),
        response_model=_StylePlan,
    )
    return _valid_styles(raw, curriculum, catalogue)


def _plan_recipes(llm, brief, curriculum, catalogue, previous, change):
    raw = llm.complete_structured(
        system=RECIPE_SYSTEM,
        prompt=_plan_prompt("recipes", brief, curriculum, catalogue, previous, change),
        response_model=_RecipePlan,
    )
    return _valid_recipes(raw, curriculum, catalogue)


# -- Keeping designs between chat turns ----------------------------------------------------------


@dataclass
class _Store:
    designs: dict[str, tuple[float, CourseDesign]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


_store = _Store()


def _keep(design: CourseDesign) -> None:
    now = time.monotonic()
    with _store.lock:
        expired = [k for k, (at, _) in _store.designs.items() if now - at > DESIGN_TTL_SECONDS]
        for key in expired:
            del _store.designs[key]
        _store.designs[design.id] = (now, design)


def get_design(design_id: str, course_id: int | None) -> CourseDesign:
    """A design proposed in this course, while it can still be revised or approved."""
    with _store.lock:
        kept = _store.designs.get(design_id)
    if kept is None or kept[1].course_id != course_id:
        raise NotFoundError(
            "That design has expired or belongs to another course. Start it again with "
            "design_curriculum."
        )
    return kept[1]


def _update(base: CourseDesign, **fields) -> CourseDesign:
    """``base``'s design with ``fields`` replaced, unless its curriculum changed meanwhile.

    The style and recipe suggesters may run at the same time on one design; each writes only
    its own fields onto the design as it is now, so neither loses the other's work.
    """
    with _store.lock:
        current = _store.designs[base.id][1]
        if current.curriculum != base.curriculum:
            raise DomainRuleError(
                "The curriculum changed while this was being planned. Suggest again."
            )
        updated = current.model_copy(update=fields)
        _store.designs[base.id] = (time.monotonic(), updated)
    return updated


# -- The steps: each one a tool the chat agent calls ----------------------------------------------


def design_curriculum(
    *,
    course_id: int | None,
    brief: DraftBrief | None = None,
    design: CourseDesign | None = None,
    change: str = "",
    draft_client: StructuredLLMClient | None = None,
) -> CourseDesign:
    """Start a design from ``brief``, or redraft ``design``'s curriculum by ``change``.

    One model call. A redrafted curriculum keeps the design's styles and recipes but drops which
    subtopic uses them, so both must be suggested again. Writes nothing to the database.

    Raises:
        DomainRuleError: neither a brief nor a design.
    """
    if brief is None and design is None:
        raise DomainRuleError("Describe the course, or name the design to revise.")
    draft = draft_taxonomy(
        brief or design.brief,  # type: ignore[union-attr]
        client=draft_client,
        current=design.curriculum if design else None,
        change=change,
    )
    if design is None:
        new = CourseDesign(
            id=uuid.uuid4().hex[:12],
            course_id=course_id,
            brief=brief,
            curriculum=draft.document,
            out_of_scope=draft.out_of_scope,
        )
        _keep(new)
        return new
    with _store.lock:
        current = _store.designs[design.id][1]
        updated = current.model_copy(
            update={
                "curriculum": draft.document,
                "out_of_scope": draft.out_of_scope,
                "style_use": None,
                "recipe_use": None,
            }
        )
        _store.designs[design.id] = (time.monotonic(), updated)
    return updated


def suggest_styles(
    design: CourseDesign,
    catalogue: DesignCatalogue,
    *,
    change: str = "",
    client: StructuredLLMClient | None = None,
) -> CourseDesign:
    """Plan (or re-plan, by ``change``) the design's question styles. One model call."""
    styles, use = _plan_styles(
        client or get_structured_client(), design.brief, design.curriculum, catalogue,
        design if design.styles else None, change,
    )  # fmt: skip
    return _update(design, styles=styles, style_use=use)


def suggest_recipes(
    design: CourseDesign,
    catalogue: DesignCatalogue,
    *,
    change: str = "",
    client: StructuredLLMClient | None = None,
) -> CourseDesign:
    """Plan (or re-plan, by ``change``) the design's tutorial recipes. One model call."""
    recipes, use = _plan_recipes(
        client or get_structured_client(), design.brief, design.curriculum, catalogue,
        design if design.recipes else None, change,
    )  # fmt: skip
    return _update(design, recipes=recipes, recipe_use=use)


def require_complete(design: CourseDesign) -> None:
    """Refuse a design whose styles or recipes are not planned for its current curriculum."""
    missing = [
        name
        for name, use in (
            ("suggest_styles", design.style_use),
            ("suggest_recipes", design.recipe_use),
        )
        if use is None
    ]
    if missing:
        raise DomainRuleError(
            "The design is not complete yet.", detail=f"Run {' and '.join(missing)} first."
        )
