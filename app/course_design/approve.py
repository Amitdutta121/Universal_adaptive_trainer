"""Approve a whole course design in one step (ADR-078).

The professor approved the design as it was shown: the curriculum, and which styles and recipes
each subtopic uses. Approving it saves the curriculum exactly as designed, drafts and saves each
new recipe from the name and summary the professor saw (one model call each, with the drafters'
own repair retry), and approves the design's recipes for the new curriculum so students see their
blocks. New styles are drafted but not saved: the professor reviews each one's example questions
on its own ``save_style`` approval card first, and a subtopic lists them as pending until then.
A draft that still fails its checks is reported, not offered; the rest of the design is saved.

No database transaction is held across a model call: each draft is read in a short session and
saved in its own, so a later draft sees the ids an earlier one took.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.course_design.design import CourseDesign, require_complete, subtopic_keys
from app.curriculum import TaxonomyImportService
from app.errors import AdaptiveTrainerError
from app.llm.client import StructuredLLMClient
from app.persistence.repositories import CurriculumRepository
from app.styles import drafting as style_drafting
from app.subjects import profile_for_course_id
from app.tutorials import experimental
from app.tutorials.approval import decide_recipe
from app.tutorials.generator import course_recipes


class ApprovedItem(BaseModel):
    name: str
    #: The saved style's or recipe's id; ``None`` when a new one could not be made.
    id: str | None
    new: bool
    #: Why a new one was not saved.
    problem: str | None = None


class StyleDraft(BaseModel):
    """A new style drafted for review; nothing is saved until ``save_style`` is approved."""

    name: str
    #: The drafted style's id, which ``save_style`` keeps.
    style_id: str
    #: Pass unchanged to ``save_style``.
    yaml: str
    #: The style's fields with its example questions, which the approval card shows.
    style: dict[str, Any]


class ApprovedSubtopic(BaseModel):
    subtopic_id: int
    topic: str
    name: str
    #: Saved styles it uses.
    style_ids: list[str]
    #: Drafted styles it uses, saved only if the professor approves them.
    pending_style_ids: list[str]
    recipe_ids: list[str]


class ApprovedDesign(BaseModel):
    curriculum_version_id: int
    styles: list[ApprovedItem]
    #: New styles to offer with ``save_style``, one approval card each.
    style_drafts: list[StyleDraft]
    recipes: list[ApprovedItem]
    #: Every subtopic with the saved styles and recipes it uses: the question setup's styles.
    subtopics: list[ApprovedSubtopic]


def approve_design(
    design: CourseDesign,
    *,
    session_factory: Callable[[], Session],
    style_client: StructuredLLMClient,
    recipe_client: StructuredLLMClient,
) -> ApprovedDesign:
    """Save ``design``'s curriculum, new recipes and recipe approvals; draft its new styles.

    One model call per new style and per new recipe (plus their repair retries).

    Raises:
        DomainRuleError and other app errors from saving the curriculum; nothing is saved then.
    """
    require_complete(design)
    assert design.style_use is not None and design.recipe_use is not None
    course_id = design.course_id
    styles: dict[str, ApprovedItem] = {}
    drafts: dict[str, StyleDraft] = {}
    for style in design.styles:
        if style.existing_id is not None:
            styles[style.key] = ApprovedItem(name=style.name, id=style.existing_id, new=False)
            continue
        with session_factory() as session:
            profile = profile_for_course_id(session, course_id)
            draft = style_drafting.draft_style(
                session, profile, style_client, _style_description(style)
            )
        problem = "; ".join(draft.problems) or None
        if problem is None and draft.style is None:
            problem = "the draft could not be read"
        if problem is None and any(d.style_id == draft.style.id for d in drafts.values()):
            problem = f"its id {draft.style.id} is used by another new style"
        styles[style.key] = ApprovedItem(name=style.name, id=None, new=True, problem=problem)
        if problem is None:
            drafts[style.key] = StyleDraft(
                name=style.name,
                style_id=draft.style.id,
                yaml=draft.yaml,
                style=draft.style.model_dump(mode="json", exclude={"subject"}),
            )

    recipes: dict[str, ApprovedItem] = {}
    for recipe in design.recipes:
        if recipe.existing_id is not None:
            recipes[recipe.key] = ApprovedItem(name=recipe.name, id=recipe.existing_id, new=False)
            continue
        with session_factory() as session:
            subject = profile_for_course_id(session, course_id).storage_key
        draft = experimental.draft_recipe(
            recipe_client,
            subject,
            f"{recipe.name}: {recipe.summary} Tutorial form: {recipe.form}.",
        )
        problem = "; ".join(draft.problems) or None
        recipe_id = None
        if problem is None and draft.recipe is not None:
            with session_factory() as session:
                profile = profile_for_course_id(session, course_id)
                taken = {r.id for r in course_recipes(session, profile.storage_key, course_id)}
                if draft.recipe.id in taken:
                    problem = f"its id {draft.recipe.id} is already used by another recipe"
                else:
                    try:
                        experimental.save_recipe(session, profile, draft.yaml)
                        session.commit()
                        recipe_id = draft.recipe.id
                    except AdaptiveTrainerError as exc:
                        problem = exc.detail or exc.message
        recipes[recipe.key] = ApprovedItem(
            name=recipe.name, id=recipe_id, new=True, problem=problem
        )

    with session_factory() as session:
        version = TaxonomyImportService(session).import_upload(
            filename="taxonomy.json",
            data=design.curriculum.model_dump_json().encode("utf-8"),
            course_id=course_id,
        )
        for recipe_id in dict.fromkeys(r.id for r in recipes.values() if r.id):
            decide_recipe(
                session, curriculum_version_id=version.id, recipe_id=recipe_id, approved=True
            )
        session.commit()
        tree = CurriculumRepository(session).get_with_tree(version.id)
        saved = [s for topic in tree.topics for s in topic.subtopics]
        subtopics = []
        # The import keeps the document's order, so the n-th saved subtopic is the n-th key.
        for row, (key, topic, name) in zip(saved, subtopic_keys(design.curriculum), strict=True):
            style_keys, recipe_keys = design.style_use[key], design.recipe_use[key]
            subtopics.append(
                ApprovedSubtopic(
                    subtopic_id=row.id,
                    topic=topic,
                    name=name,
                    style_ids=[i for k in style_keys if (i := styles[k].id)],
                    pending_style_ids=[drafts[k].style_id for k in style_keys if k in drafts],
                    recipe_ids=[i for k in recipe_keys if (i := recipes[k].id)],
                )
            )
        version_id = version.id

    return ApprovedDesign(
        curriculum_version_id=version_id,
        styles=list(styles.values()),
        style_drafts=list(drafts.values()),
        recipes=list(recipes.values()),
        subtopics=subtopics,
    )


def _style_description(style) -> str:
    figure = "" if style.figure == "none" else f" Figure: {style.figure}."
    return f"{style.name}: {style.summary} Question type: {style.question_type}.{figure}"
