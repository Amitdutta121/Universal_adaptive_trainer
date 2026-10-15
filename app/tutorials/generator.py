"""Generate one tutorial block: recipe + retrieved chunks + tool output -> one model call (Task 21).

The block's payload is checked against its renderer's contract (``app/tutorials/renderers.py``),
and an html block is loaded headless (``app/tutorials/html_check.py``).
An invalid payload -- or an unreadable reply -- gets one repair retry that shows the model what
was wrong; a second failure saves the block as ``failed`` with the reason, so a professor sees
what was tried. There is no groundedness judge: the block stores the ids of the chunks it was
written from.

For a ``python_trace`` recipe the model writes a program and notes, never the run: the code is
traced (``app/tutorials/tools/python_trace.py``) and the recorded steps are embedded as-is in
the stepper's html. Code the caller gives (e.g. the question a student got wrong) is traced
before the call, and the model writes notes for it.

A ``video_clip`` recipe calls no model at all: the block is the course video's chunk that the
subtopic retrieves best, as a clip (``app/tutorials/clips.py``, Task 31).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.chunks import HEADING_SEPARATOR
from app.domain.enums import (
    ChunkSourceKind,
    GuidanceLevel,
    TutorialBlockStatus,
    TutorialRenderer,
)
from app.errors import DomainRuleError, MalformedModelOutputError, NotFoundError
from app.llm import ChatTurn, StructuredLLMClient
from app.persistence.models import TutorialBlockRow
from app.persistence.repositories import ChunkRepository, CurriculumRepository
from app.retrieval.chunks import ChunkRetriever
from app.subjects import profile_for_version
from app.tutorials.approval import initial_status
from app.tutorials.clips import clip_payload
from app.tutorials.html_check import HtmlCheckUnavailable, check_html_block
from app.tutorials.loader import load_recipes
from app.tutorials.renderers import (
    ChartPayload,
    HtmlPayload,
    MarkdownPayload,
    MermaidPayload,
    StepperDraft,
    StepperPayload,
    payload_problems,
    stepper_html,
    stepper_problems,
)
from app.tutorials.schema import RecipeCheck, RecipeInput, RecipeTool, TutorialRecipe
from app.tutorials.tools.python_trace import TraceResult, python_trace
from app.validation.runner import LocalCodeRunner

logger = logging.getLogger(__name__)

#: Chunks retrieved for a block, and characters of each shown to the model.
TOP_K_CHUNKS = 4
EXCERPT_CHARS = 1500
#: The first call and the one repair retry.
MAX_ATTEMPTS = 2

GUIDANCE = {
    GuidanceLevel.WORKED: (
        "WORKED: the student has not got this yet. Show the whole idea worked through, every "
        "step explained."
    ),
    GuidanceLevel.FADED: (
        "FADED: the student is partly there. Explain the first steps, then leave the last "
        "step or two for the student to work out, saying what to look at."
    ),
    GuidanceLevel.CUE: (
        "CUE: the student nearly has it. One short reminder of the key idea, no worked solution."
    ),
}

SYSTEM = (
    "You write one short tutorial block for a student of an introductory course. Teach only "
    "what the book excerpts teach, in their terms. Follow the recipe's instructions and the "
    "guidance level exactly, and answer only in the requested structure."
)

_DRAFTS: dict[TutorialRenderer, type[BaseModel]] = {
    TutorialRenderer.MARKDOWN: MarkdownPayload,
    TutorialRenderer.MERMAID: MermaidPayload,
    TutorialRenderer.CHARTJS: ChartPayload,
    TutorialRenderer.HTML: HtmlPayload,
}


@cache
def _recipes() -> dict[str, list[TutorialRecipe]]:
    return load_recipes()


def get_recipes(subject: str) -> list[TutorialRecipe]:
    """Every recipe of one subject (a subject storage key); ``[]`` for a subject with none."""
    return list(_recipes().get(subject, []))


def get_recipe(subject: str, recipe_id: str) -> TutorialRecipe:
    for recipe in get_recipes(subject):
        if recipe.id == recipe_id:
            return recipe
    raise NotFoundError(f"No tutorial recipe {recipe_id!r} for this subject.")


#: Loads an html block headless and returns its problems (``app/tutorials/html_check.py``).
HtmlCheck = Callable[[dict[str, Any], list[RecipeCheck]], list[str]]


@dataclass(frozen=True)
class BlockRequest:
    subtopic_id: int
    recipe_id: str
    guidance_level: GuidanceLevel
    #: Code to trace, for a ``python_trace`` recipe; without it the model writes the program.
    code: str | None = None


def draft_model(recipe: TutorialRecipe) -> type[BaseModel]:
    """The structure the model answers in for this recipe (not called for a ``video_clip``)."""
    if recipe.tool is RecipeTool.PYTHON_TRACE:
        return StepperDraft
    return _DRAFTS[recipe.renderer]


def build_prompt(
    recipe: TutorialRecipe,
    level: GuidanceLevel,
    subtopic: str,
    excerpts: list[tuple[str, str]],
    *,
    code: str | None = None,
    trace: TraceResult | None = None,
) -> str:
    parts = [
        f"Recipe: {recipe.name}. {recipe.summary}",
        recipe.prompt.strip(),
        f"Guidance level: {GUIDANCE[level]}",
        f"Subtopic: {subtopic}",
        "Book excerpts:",
        *(f"[{n}] {heading}\n{text}" for n, (heading, text) in enumerate(excerpts, start=1)),
    ]
    if code is not None:
        numbered = "\n".join(f"{n:>3}| {line}" for n, line in enumerate(code.splitlines(), 1))
        parts.append(
            "Use exactly this program (leave the code field empty); write notes for its lines:\n"
            + numbered
        )
        if trace is not None:
            parts.append(f"Running it printed:\n{trace.stdout or '(nothing)'}")
    return "\n\n".join(parts)


def _excerpts(session: Session, chunk_ids: list[str]) -> list[tuple[str, str]]:
    rows = ChunkRepository(session).get_many(chunk_ids)
    return [
        (HEADING_SEPARATOR.join(rows[c].heading_path or []), rows[c].text[:EXCERPT_CHARS])
        for c in chunk_ids
        if c in rows
    ]


def _payload(
    recipe: TutorialRecipe,
    draft: BaseModel,
    *,
    code: str | None,
    trace: TraceResult | None,
    runner: LocalCodeRunner | None,
) -> tuple[dict[str, Any], list[str]]:
    """The payload built from a draft, and why it is invalid (``[]`` when it is valid)."""
    if not isinstance(draft, StepperDraft):
        payload = draft.model_dump(mode="json")
        return payload, payload_problems(recipe.renderer, payload)
    program = code if code is not None else draft.code
    if not program.strip():
        return {}, ["the code field is empty: write the Python program"]
    if trace is None or code is None:
        trace = python_trace(program, runner=runner)
    problems = stepper_problems(program, trace.error, len(trace.steps), draft.notes)
    if problems:
        return {}, problems
    payload = StepperPayload(
        title=draft.title,
        code=program,
        trace=trace.steps,
        notes=draft.notes,
        html=stepper_html(draft.title, program, trace.steps, draft.notes),
    ).model_dump(mode="json")
    return payload, payload_problems(recipe.renderer, payload)


def generate_block(
    session: Session,
    request: BlockRequest,
    *,
    client: StructuredLLMClient,
    retriever: ChunkRetriever,
    runner: LocalCodeRunner | None = None,
    html_check: HtmlCheck = check_html_block,
) -> TutorialBlockRow:
    """Generate, check and save one block (flushed, not committed); ``failed`` if still invalid.

    Raises:
        NotFoundError: the subtopic or the recipe does not exist.
        DomainRuleError: the recipe has no such guidance level, code was given to a recipe that
            does not trace code, given code does not run, or no chunk was found to write from.
    """
    subtopic = CurriculumRepository(session).get_subtopic(request.subtopic_id)
    subject = profile_for_version(session, subtopic.topic.curriculum_version_id).storage_key
    recipe = get_recipe(subject, request.recipe_id)
    if request.guidance_level not in recipe.guidance_levels:
        allowed = ", ".join(level.value for level in recipe.guidance_levels)
        raise DomainRuleError(
            f"Recipe {recipe.id} is written at {allowed}, not {request.guidance_level.value}."
        )
    if recipe.tool is RecipeTool.VIDEO_CLIP:
        return _clip_block(session, subtopic, recipe, request, retriever)
    trace: TraceResult | None = None
    if request.code is not None:
        if RecipeInput.CODE not in recipe.inputs:
            raise DomainRuleError(f"Recipe {recipe.id} does not take code.")
        trace = python_trace(request.code, runner=runner)
        if trace.error is not None:
            raise DomainRuleError("The given code does not run to the end.", detail=trace.error)

    found = retriever.for_subtopic(request.subtopic_id, top_k=TOP_K_CHUNKS)
    chunk_ids = [chunk.chunk_id for chunk in found]
    if not chunk_ids:
        raise DomainRuleError(
            "No book text was found for this subtopic, so there is nothing to write the "
            "tutorial from. Import the course's book first."
        )
    subtopic_text = f"{subtopic.topic.name} - {subtopic.name}" + (
        f": {subtopic.description}" if subtopic.description else ""
    )
    prompt = build_prompt(
        recipe,
        request.guidance_level,
        subtopic_text,
        _excerpts(session, chunk_ids),
        code=request.code,
        trace=trace,
    )
    response_model = draft_model(recipe)

    history: list[ChatTurn] = []
    asking = prompt
    problems: list[str] = []
    payload: dict[str, Any] = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            draft = client.complete_structured(
                system=SYSTEM,
                prompt=asking,
                response_model=response_model,
                **({"history": tuple(history)} if history else {}),
            )
        except MalformedModelOutputError as exc:
            problems = [f"the reply did not match the requested structure ({exc.detail or ''})"]
            asking = f"{prompt}\n\n{_correction(problems)}"
            continue
        payload, problems = _payload(recipe, draft, code=request.code, trace=trace, runner=runner)
        if not problems and recipe.renderer is TutorialRenderer.HTML:
            try:
                problems = html_check(payload, list(recipe.checks))
            except HtmlCheckUnavailable as exc:
                # Not the model's fault, so no retry; never ship html nobody has loaded.
                problems = [str(exc)]
                break
        if not problems:
            break
        logger.info("Tutorial block attempt %s/%s invalid: %s", attempt, MAX_ATTEMPTS, problems)
        history = [("user", prompt), ("assistant", json.dumps(draft.model_dump(mode="json")))]
        asking = _correction(problems)

    block = TutorialBlockRow(
        subtopic_id=subtopic.id,
        recipe_id=recipe.id,
        guidance_level=request.guidance_level,
        renderer=recipe.renderer,
        payload=payload if not problems else {},
        chunk_ids=chunk_ids,
        status=TutorialBlockStatus.FAILED
        if problems
        else initial_status(session, subtopic.topic.curriculum_version_id, recipe.id),
        error="; ".join(problems) if problems else None,
        model=client.description,
    )
    session.add(block)
    session.flush()
    return block


def _clip_block(
    session: Session,
    subtopic,
    recipe: TutorialRecipe,
    request: BlockRequest,
    retriever: ChunkRetriever,
) -> TutorialBlockRow:
    """The block of a ``video_clip`` recipe: the best-matching video chunk, no model call."""
    found = retriever.for_subtopic(request.subtopic_id, top_k=1, source_kind=ChunkSourceKind.VIDEO)
    if not found:
        raise DomainRuleError(
            "No playable course video was found for this subtopic. Import a YouTube video "
            "for the course first."
        )
    chunk = ChunkRepository(session).get_many([found[0].chunk_id])[found[0].chunk_id]
    payload = clip_payload(chunk)
    problems = payload_problems(recipe.renderer, payload)
    block = TutorialBlockRow(
        subtopic_id=subtopic.id,
        recipe_id=recipe.id,
        guidance_level=request.guidance_level,
        renderer=recipe.renderer,
        payload=payload if not problems else {},
        chunk_ids=[chunk.id],
        status=TutorialBlockStatus.FAILED
        if problems
        else initial_status(session, subtopic.topic.curriculum_version_id, recipe.id),
        error="; ".join(problems) if problems else None,
        model="",
    )
    session.add(block)
    session.flush()
    return block


def _correction(problems: list[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return f"The block above cannot be used:\n{listed}\nWrite it again, fixing these."
