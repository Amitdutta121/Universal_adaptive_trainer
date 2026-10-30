"""The agent's tutorial-recipe tools, and ``import_material`` behind approval. LLM is faked."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_tutorial_generator import QueuedClient
from test_tutorial_routes import FlatEmbedder

from app.persistence.database import get_session_factory
from app.persistence.models import (
    BookRow,
    ExperimentalRecipeRow,
    SubtopicRow,
    TutorialBlockRow,
)
from app.tutorials.serving import servable_recipes
from tests.agent_support import result_of, run
from tests.test_experimental_recipes import DRAFT, RECIPE, _course, _subtopic, _yaml
from tests.test_youtube_source import URL, Fakes


@pytest.fixture
def db(client: TestClient) -> Iterator[None]:
    """The app's schema, created by the client's lifespan; tools open their own sessions."""
    yield


def _setup() -> tuple[int, int, int]:
    """A Python course with a book and one subtopic: (course id, subtopic id, version id)."""
    with get_session_factory()() as session:
        course = _course(session)
        subtopic_id = _subtopic(session, course)
        version_id = session.get(SubtopicRow, subtopic_id).topic.curriculum_version_id
        return int(course["X-Course-Id"]), subtopic_id, version_id


def _saved_rows() -> list[ExperimentalRecipeRow]:
    with get_session_factory()() as session:
        return list(session.scalars(select(ExperimentalRecipeRow)))


def test_draft_recipe_drafts_with_the_tutorial_model_and_saves_nothing(db) -> None:
    course_id, _, _ = _setup()
    tutor = QueuedClient(DRAFT)

    messages = run(
        ("draft_recipe", {"description": "explain with an analogy"}),
        course_id=course_id,
        tutorial_client=tutor,
    ).all_messages()

    drafted = result_of(messages, "draft_recipe")
    assert drafted.problems == []
    assert yaml.safe_load(drafted.yaml)["id"] == RECIPE["id"]
    assert "explain with an analogy" in tutor.calls[0]["prompt"]
    assert _saved_rows() == []


def test_try_recipe_writes_one_block_and_saves_nothing(db) -> None:
    course_id, subtopic_id, _ = _setup()

    messages = run(
        ("try_recipe", {"yaml": _yaml(), "subtopic_id": subtopic_id}),
        course_id=course_id,
        tutorial_client=QueuedClient({"markdown": "A loop is like dealing cards."}),
        embedder=FlatEmbedder,
    ).all_messages()

    tried = result_of(messages, "try_recipe")
    assert (tried.error, tried.payload) == (None, {"markdown": "A loop is like dealing cards."})
    assert _saved_rows() == []
    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(TutorialBlockRow)) == 0


def test_save_recipe_waits_for_approval_then_replaces_by_id(db) -> None:
    course_id, _, _ = _setup()
    save = ("save_recipe", {"yaml": _yaml()})

    run(save, course_id=course_id)  # no click yet
    assert _saved_rows() == []

    run(save, decision=False, course_id=course_id)
    assert _saved_rows() == []

    saved = result_of(run(save, decision=True, course_id=course_id).all_messages(), "save_recipe")
    assert saved.recipe_id == RECIPE["id"]
    run(
        ("save_recipe", {"yaml": _yaml(name="Analogy, then its limits")}),
        decision=True,
        course_id=course_id,
    )
    rows = _saved_rows()
    assert len(rows) == 1
    assert "Analogy, then its limits" in rows[0].yaml


def test_decide_recipe_puts_a_saved_recipe_in_front_of_students_once_approved(db) -> None:
    course_id, _, version_id = _setup()
    run(("save_recipe", {"yaml": _yaml()}), decision=True, course_id=course_id)

    def served() -> bool:
        with get_session_factory()() as session:
            return RECIPE["id"] in servable_recipes(session, "intro_python", course_id, version_id)

    decide = (
        "decide_recipe",
        {"recipe_id": RECIPE["id"], "curriculum_version_id": version_id, "approved": True},
    )
    run(decide, course_id=course_id)  # waiting for the click
    assert not served()

    run(decide, decision=True, course_id=course_id)
    assert served()

    listed = result_of(
        run(
            ("list_recipes", {"curriculum_version_id": version_id}), course_id=course_id
        ).all_messages(),
        "list_recipes",
    )
    own = next(recipe for recipe in listed.recipes if recipe.recipe_id == RECIPE["id"])
    assert (own.made_for_course, own.decision) == (True, "approved")
    assert any(not recipe.made_for_course for recipe in listed.recipes)


def test_import_material_now_waits_for_approval(db) -> None:
    fakes = Fakes()

    run(("import_material", {"url": URL}), youtube_fetch=fakes.fetch, youtube_check=fakes.check)

    assert fakes.fetched == []
    with get_session_factory()() as session:
        assert session.scalars(select(BookRow)).all() == []
