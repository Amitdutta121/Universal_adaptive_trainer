"""The experimental recipe builder: tutorial recipes written with AI, kept per course.

A check on whether professors (or a chatbot) can make recipes at all. A recipe here is YAML
validated as a :class:`TutorialRecipe` with the library's rules, plus the pairings the generator
relies on (``python_trace`` draws html; ``trace_matches`` needs ``python_trace``). It can be
drafted or revised by the model, saved, edited and deleted, and *tried*: one block written for a
real subtopic through the library's own generator (:func:`write_block`), shown and never saved.

A saved recipe joins the course's recipes (``course_recipes`` in ``generator.py``): it is listed
on the tutorials page beside the library's, can be approved per taxonomy, and reaches students
only once approved (``servable_recipes`` in ``serving.py``). Editing or deleting one hides the
blocks it already wrote. Ids start with ``exp.`` so they never collide with a library id.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import yaml
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import GuidanceLevel, TutorialBlockStatus, TutorialRenderer
from app.errors import DomainRuleError, MalformedModelOutputError, NotFoundError
from app.llm import ChatTurn, StructuredLLMClient
from app.persistence.models import (
    CurriculumVersionRow,
    ExperimentalRecipeRow,
    SubtopicRow,
    TopicRow,
    TutorialBlockRow,
)
from app.retrieval.chunks import ChunkRetriever
from app.styles.loader import _Dumper
from app.subjects import SubjectProfile
from app.tutorials.generator import BlockRequest, get_recipes, write_block
from app.tutorials.schema import (
    ContentKind,
    RecipeCheck,
    RecipeInput,
    RecipeTool,
    TutorialRecipe,
)

PREFIX = "exp."
_ID = re.compile(r"^exp\.[a-z][a-z0-9_]{0,60}$")
#: The first draft and the one repair retry, as for a tutorial block.
MAX_ATTEMPTS = 2


def _problems(recipe: TutorialRecipe) -> list[str]:
    """What the generator would trip on that the schema alone does not catch."""
    problems: list[str] = []
    if not _ID.match(recipe.id):
        problems.append(f"id must look like {PREFIX}snake_case_name, got {recipe.id!r}")
    if recipe.tool is RecipeTool.PYTHON_TRACE and recipe.renderer is not TutorialRenderer.HTML:
        problems.append("a python_trace recipe draws a stepper, so its renderer must be html")
    if RecipeCheck.TRACE_MATCHES in recipe.checks and recipe.tool is not RecipeTool.PYTHON_TRACE:
        problems.append("the trace_matches check needs the python_trace tool")
    if RecipeCheck.HTML_LOADS in recipe.checks and recipe.renderer is not TutorialRenderer.HTML:
        problems.append("the html_loads check needs the html renderer")
    if RecipeInput.CODE in recipe.inputs and recipe.tool is not RecipeTool.PYTHON_TRACE:
        problems.append("only a python_trace recipe takes code as an input")
    return problems


def parse_recipe(text: str, subject: str) -> TutorialRecipe:
    """``text`` as a valid experimental recipe of ``subject``.

    Raises:
        DomainRuleError: not YAML, not a mapping, a field the schema refuses, or a pairing the
            generator cannot run; ``detail`` lists every problem.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DomainRuleError("This recipe is not valid YAML.", detail=str(exc)) from exc
    if not isinstance(data, dict):
        raise DomainRuleError("A recipe is a mapping of fields, like the library's files.")
    data["subject"] = subject
    try:
        recipe = TutorialRecipe.model_validate(data)
    except ValidationError as exc:
        raise DomainRuleError(
            "This recipe does not fit the recipe schema.",
            detail="\n".join(
                f"{'.'.join(str(part) for part in error['loc']) or 'recipe'}: {error['msg']}"
                for error in exc.errors()
            ),
        ) from exc
    if problems := _problems(recipe):
        raise DomainRuleError("This recipe cannot be generated from.", detail="\n".join(problems))
    return recipe


def dump_recipe(recipe: TutorialRecipe) -> str:
    """The recipe as a library-style file (subject left to the path)."""
    data = recipe.model_dump(mode="json", exclude={"subject"}, exclude_none=True)
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


# -- Stored recipes -----------------------------------------------------------------------------


def _course(profile: SubjectProfile) -> int:
    if profile.course_id is None:
        raise DomainRuleError("Experimental recipes belong to a course; open one first.")
    return profile.course_id


def list_recipes(session: Session, profile: SubjectProfile) -> list[ExperimentalRecipeRow]:
    return list(
        session.scalars(
            select(ExperimentalRecipeRow)
            .where(ExperimentalRecipeRow.course_id == _course(profile))
            .order_by(ExperimentalRecipeRow.updated_at.desc(), ExperimentalRecipeRow.id.desc())
        )
    )


def get_row(session: Session, profile: SubjectProfile, row_id: int) -> ExperimentalRecipeRow:
    row = session.get(ExperimentalRecipeRow, row_id)
    if row is None or row.course_id != _course(profile):
        raise NotFoundError(f"Experimental recipe {row_id} not found.")
    return row


def _ensure_free(session: Session, course_id: int, recipe_id: str, keep: int | None = None) -> None:
    taken = session.scalar(
        select(ExperimentalRecipeRow.id).where(
            ExperimentalRecipeRow.course_id == course_id,
            ExperimentalRecipeRow.recipe_id == recipe_id,
        )
    )
    if taken is not None and taken != keep:
        raise DomainRuleError(
            "This course already has a recipe with this id.", detail=f"Taken: {recipe_id}."
        )


def save_recipe(
    session: Session, profile: SubjectProfile, text: str, row_id: int | None = None
) -> ExperimentalRecipeRow:
    """Create (``row_id`` ``None``) or replace a recipe; flushed, not committed."""
    course_id = _course(profile)
    recipe = parse_recipe(text, profile.storage_key)
    row = get_row(session, profile, row_id) if row_id is not None else None
    _ensure_free(session, course_id, recipe.id, keep=row.id if row else None)
    if row is None:
        row = ExperimentalRecipeRow(course_id=course_id, recipe_id=recipe.id, yaml=text)
        session.add(row)
    else:
        if row.yaml != text:
            # Its blocks were written from the old wording; students get freshly written ones.
            _retire_blocks(session, course_id, row.recipe_id)
        row.recipe_id, row.yaml = recipe.id, text
    session.flush()
    return row


def delete_recipe(session: Session, profile: SubjectProfile, row_id: int) -> None:
    row = get_row(session, profile, row_id)
    # So a later recipe that reuses the id does not inherit them.
    _retire_blocks(session, row.course_id, row.recipe_id)
    session.delete(row)
    session.flush()


def _retire_blocks(session: Session, course_id: int, recipe_id: str) -> int:
    """Hide the course's bank blocks of ``recipe_id`` (copies frozen with a set stay)."""
    subtopics = (
        select(SubtopicRow.id)
        .join(TopicRow, TopicRow.id == SubtopicRow.topic_id)
        .join(CurriculumVersionRow, CurriculumVersionRow.id == TopicRow.curriculum_version_id)
        .where(CurriculumVersionRow.course_id == course_id)
    )
    blocks = session.scalars(
        select(TutorialBlockRow).where(
            TutorialBlockRow.recipe_id == recipe_id,
            TutorialBlockRow.set_version_id.is_(None),
            TutorialBlockRow.status != TutorialBlockStatus.REJECTED,
            TutorialBlockRow.subtopic_id.in_(subtopics),
        )
    ).all()
    for block in blocks:
        block.status = TutorialBlockStatus.REJECTED
    return len(blocks)


# -- Drafting with the model --------------------------------------------------------------------


class RecipeDraft(BaseModel):
    """What the model writes; the builder turns it into a :class:`TutorialRecipe`."""

    slug: str = Field(description="snake_case, at most 40 characters; the id becomes exp.<slug>")
    name: str = Field(description="Short, as a professor would say it")
    summary: str = Field(description="One sentence on what the student sees")
    renderer: TutorialRenderer
    prompt: str = Field(description="Instructions to the block writer; empty only for video_clip")
    fits: list[ContentKind]
    guidance_levels: list[GuidanceLevel]
    inputs: list[RecipeInput]
    tool: RecipeTool | None = None
    checks: list[RecipeCheck] = Field(default_factory=list)

    def recipe(self, subject: str) -> TutorialRecipe:
        # Models often repeat the prefix or use spaces and dashes; the id is built, not trusted.
        slug = self.slug.strip().lower().removeprefix(PREFIX)
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")[:60] or "recipe"
        if not slug[0].isalpha():
            slug = f"r_{slug}"[:60]
        return TutorialRecipe.model_validate(
            {
                **self.model_dump(mode="json", exclude={"slug"}),
                "id": f"{PREFIX}{slug}",
                "subject": subject,
            }
        )


DRAFT_SYSTEM = """\
You design tutorial recipes for an adaptive tutoring system. A recipe is a reusable way of
teaching one kind of content. For every subtopic of a course, a block writer model is given the
recipe's prompt, the subtopic, a guidance level and excerpts of the course book, and writes one
short block that a trusted renderer draws for a student.

Renderers and what the block writer must produce for each:
- markdown: Markdown text (code fences allowed).
- mermaid: Mermaid diagram source plus a one-sentence caption.
- chartjs: a Chart.js spec (bar, line, pie, doughnut or scatter; labels and datasets of numbers)
  plus a caption.
- html: a self-contained HTML page with inline CSS and JS. It runs sandboxed with no network, so
  no external scripts, fonts or images.
- video_clip: no writer at all; the system picks the course video's stretch for the subtopic.
  A video_clip recipe has tool video_clip and an empty prompt.

Tools: python_trace runs a short Python program the writer produces and shows a line-by-line
stepper of the real run; it needs renderer html, and may take code as an input. Never ask the
writer to invent program output: only python_trace shows real runs.
Checks: html_loads (html renderer: loads the page headless, a console error fails it) and
trace_matches (python_trace only: the stepper must show the recorded steps).
Guidance levels: worked (everything worked through), faded (first steps shown, the student
finishes), cue (one short reminder). List only the levels the recipe can really be written at.
Inputs: subtopic and chunks always; code only with python_trace.
fits: which kinds of content the recipe teaches well: concept, process, code, misconception.

Write the prompt as direct instructions to the block writer: what to write, its shape and length,
and to use only the book excerpts' ideas and terms. Keep blocks short; a student reads one in
under a minute."""


def _draft_prompt(subject: str, description: str, current: str | None) -> str:
    examples = "\n---\n".join(dump_recipe(r) for r in get_recipes(subject)[:3])
    parts = [
        f"Recipes already in the {subject} library, for their shape:\n{examples}",
    ]
    if current:
        parts.append(f"The recipe to revise:\n{current}")
        parts.append(f"Revise it as the professor asks: {description}")
    else:
        parts.append(f"Design a new recipe for what the professor asks: {description}")
    return "\n\n".join(parts)


@dataclass(frozen=True)
class DraftResult:
    yaml: str
    #: Empty when the draft is valid; otherwise why it still is not, after the retry.
    problems: list[str]
    #: The parsed recipe when the draft is valid, for showing it without reading YAML.
    recipe: TutorialRecipe | None = None


def draft_recipe(
    client: StructuredLLMClient,
    subject: str,
    description: str,
    current_yaml: str | None = None,
) -> DraftResult:
    """A recipe drafted (or ``current_yaml`` revised) from the professor's words. Saves nothing.

    An invalid draft gets one repair retry that names the problems; if it is still invalid, the
    last draft comes back with them, so the professor can fix it by hand.
    """
    prompt = _draft_prompt(subject, description, current_yaml)
    history: list[ChatTurn] = []
    asking = prompt
    last_yaml = current_yaml or ""
    problems: list[str] = []
    recipe: TutorialRecipe | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            draft = client.complete_structured(
                system=DRAFT_SYSTEM,
                prompt=asking,
                response_model=RecipeDraft,
                **({"history": tuple(history)} if history else {}),
            )
        except MalformedModelOutputError as exc:
            problems = [f"the reply did not match the requested structure ({exc.detail or ''})"]
            asking = f"{prompt}\n\nYour last reply could not be read: {problems[0]}. Try again."
            continue
        try:
            recipe = draft.recipe(subject)
            problems = _problems(recipe)
            last_yaml = dump_recipe(recipe)
        except ValidationError as exc:
            recipe = None
            problems = [
                f"{'.'.join(str(part) for part in error['loc']) or 'recipe'}: {error['msg']}"
                for error in exc.errors()
            ]
            last_yaml = yaml.dump(
                draft.model_dump(mode="json"), Dumper=_Dumper, sort_keys=False, width=100
            )
        if not problems:
            break
        history = [("user", prompt), ("assistant", json.dumps(draft.model_dump(mode="json")))]
        listed = "\n".join(f"- {problem}" for problem in problems)
        asking = f"That recipe cannot be used:\n{listed}\nWrite it again, fixing these."
    return DraftResult(yaml=last_yaml, problems=problems, recipe=None if problems else recipe)


# -- Trying a recipe ----------------------------------------------------------------------------


def try_recipe(
    session: Session,
    profile: SubjectProfile,
    text: str,
    *,
    subtopic_id: int,
    guidance_level: GuidanceLevel,
    client: StructuredLLMClient,
    retriever: ChunkRetriever,
) -> TutorialBlockRow:
    """One block of the recipe in ``text`` for a subtopic, written and checked like a library
    block, then thrown away: the returned row is never added to the session."""
    recipe = parse_recipe(text, profile.storage_key)
    return write_block(
        session,
        BlockRequest(subtopic_id=subtopic_id, recipe_id=recipe.id, guidance_level=guidance_level),
        recipe,
        client=client,
        retriever=retriever,
    )
