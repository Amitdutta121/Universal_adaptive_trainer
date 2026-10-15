"""Tutorial recipes and the tutorial_blocks table (Phase 5, Task 19)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import GuidanceLevel, TutorialBlockStatus, TutorialRenderer
from app.persistence.models import CurriculumVersionRow, SubtopicRow, TopicRow, TutorialBlockRow
from app.styles.checks import check_ids, check_lock, read_lock
from app.tutorials.checks import check_recipe
from app.tutorials.loader import RECIPES_DIR, RecipeFileError, load_recipes, load_subject
from app.tutorials.schema import RecipeTool, TutorialRecipe

RECIPES = load_recipes()
ALL_RECIPES = [recipe for recipes in RECIPES.values() for recipe in recipes]


def test_the_seed_recipes_ship() -> None:
    by_id = {recipe.id: recipe for recipe in RECIPES["intro_python"]}
    assert set(by_id) == {
        "py.code_trace_stepper",
        "py.topic_flow",
        "py.misconception_line",
        "py.video_clip",
    }
    stepper = by_id["py.code_trace_stepper"]
    assert (stepper.renderer, stepper.tool) == (TutorialRenderer.HTML, RecipeTool.PYTHON_TRACE)
    assert by_id["py.topic_flow"].renderer is TutorialRenderer.MERMAID
    assert by_id["py.misconception_line"].renderer is TutorialRenderer.MARKDOWN
    clip = by_id["py.video_clip"]
    assert (clip.renderer, clip.tool) == (TutorialRenderer.VIDEO_CLIP, RecipeTool.VIDEO_CLIP)
    assert clip.guidance_levels == [GuidanceLevel.WORKED]


# ------------------------------------------------------------------ CI checks (mirror Task 17)


@pytest.mark.parametrize("recipe", ALL_RECIPES, ids=lambda recipe: recipe.id)
def test_every_recipe_is_coherent(recipe: TutorialRecipe) -> None:
    assert check_recipe(recipe) == []


def test_ids_are_namespaced_unique_and_locked() -> None:
    assert check_ids(RECIPES) == []
    locked = read_lock(RECIPES_DIR / "ids.lock")
    assert check_lock(RECIPES, locked, lock="recipes/ids.lock", noun="recipe") == []


def test_a_removed_or_new_id_fails_the_lock() -> None:
    locked = read_lock(RECIPES_DIR / "ids.lock")
    without = {"intro_python": [r for r in ALL_RECIPES if r.id != "py.topic_flow"]}
    (problem,) = check_lock(without, locked, lock="recipes/ids.lock", noun="recipe")
    assert problem.startswith("intro_python/py.topic_flow: in recipes/ids.lock but its recipe")
    renamed = {"intro_python": [*ALL_RECIPES, ALL_RECIPES[0].model_copy(update={"id": "py.x"})]}
    problems = check_lock(renamed, locked, lock="recipes/ids.lock", noun="recipe")
    assert problems == [
        "intro_python/py.x: new recipe id not in recipes/ids.lock; "
        "add the line 'intro_python/py.x' to it"
    ]


def test_a_duplicate_or_unnamespaced_id_fails() -> None:
    recipe = ALL_RECIPES[0]
    assert any("duplicate id" in p for p in check_ids({"a": [recipe], "b": [recipe]}))
    bad = recipe.model_copy(update={"id": "NoPrefix"})
    assert check_ids({"intro_python": [bad]}) == [
        "intro_python/NoPrefix: id must look like '<prefix>.<snake_case_name>'"
    ]


def test_an_incoherent_recipe_names_the_rule() -> None:
    stepper = next(r for r in ALL_RECIPES if r.tool is RecipeTool.PYTHON_TRACE)
    as_markdown = stepper.model_copy(update={"renderer": TutorialRenderer.MARKDOWN})
    assert any("needs the html renderer" in p for p in check_recipe(as_markdown))
    no_check = stepper.model_copy(update={"checks": []})
    problems = check_recipe(no_check)
    assert any("'html_loads'" in p for p in problems)
    assert any("'trace_matches'" in p for p in problems)


def test_recipe_schema_json_is_current() -> None:
    from scripts.export_recipe_schema import SCHEMA_PATH, recipe_file_schema

    assert SCHEMA_PATH.read_text(encoding="utf-8").replace("\r\n", "\n") == recipe_file_schema(), (
        "recipes/schema.json is stale; run: python -m scripts.export_recipe_schema"
    )


_MINIMAL = """name: N
summary: S
renderer: markdown
prompt: Write it.
fits: [concept]
guidance_levels: [cue]
inputs: [subtopic, chunks]
"""


def test_a_bad_recipe_file_names_the_file_and_the_field(tmp_path: Path) -> None:
    subject = tmp_path / "intro_python"
    subject.mkdir()
    (subject / "py.bad.yaml").write_text(_MINIMAL.replace("markdown", "pdf"), encoding="utf-8")
    with pytest.raises(RecipeFileError, match=r"py\.bad\.yaml.*field 'renderer'"):
        load_subject(subject)
    (subject / "py.bad.yaml").write_text("id: py.other\n" + _MINIMAL, encoding="utf-8")
    with pytest.raises(RecipeFileError, match=r"py\.bad\.yaml: field 'id'"):
        load_subject(subject)


# ------------------------------------------------------------------ tutorial_blocks


def _subtopic(session: Session) -> SubtopicRow:
    version = CurriculumVersionRow(label="Intro")
    topic = TopicRow(name="Loops", subtopics=[SubtopicRow(name="while loops")])
    version.topics.append(topic)
    session.add(version)
    session.commit()
    return topic.subtopics[0]


def _block(subtopic: SubtopicRow, **fields: object) -> TutorialBlockRow:
    return TutorialBlockRow(
        subtopic_id=subtopic.id,
        recipe_id="py.misconception_line",
        guidance_level=GuidanceLevel.CUE,
        renderer=TutorialRenderer.MARKDOWN,
        payload={"markdown": "**x**"},
        **fields,
    )


def test_a_block_round_trips_with_its_chunks(session: Session) -> None:
    subtopic = _subtopic(session)
    block = _block(subtopic, chunk_ids=["c1", "c2"])
    session.add(block)
    session.commit()
    session.expire_all()
    stored = session.get(TutorialBlockRow, block.id)
    assert stored is not None
    assert stored.chunk_ids == ["c1", "c2"]
    assert stored.status is TutorialBlockStatus.DRAFT
    assert stored.payload == {"markdown": "**x**"}


def test_a_block_without_chunk_ids_cannot_be_saved(session: Session) -> None:
    subtopic = _subtopic(session)
    with pytest.raises(ValueError, match="chunk_ids"):
        _block(subtopic, chunk_ids=[])
    # Leaving chunk_ids out skips the ORM check; the table's own constraint refuses it.
    session.add(_block(subtopic))
    with pytest.raises(IntegrityError):
        session.commit()
