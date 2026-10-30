"""The experimental recipe builder: draft with AI, save, edit, delete, try. LLM is faked."""

from __future__ import annotations

from collections.abc import Iterator

import book_documents as docs
import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_tutorial_generator import QueuedClient
from test_tutorial_routes import FlatEmbedder

from app.domain.enums import GuidanceLevel, TutorialBlockStatus, TutorialRenderer
from app.persistence.models import (
    CourseRow,
    CurriculumVersionRow,
    SubtopicRow,
    TopicRow,
    TutorialBlockRow,
)
from app.tutorials.serving import servable_recipes
from app.web.routes.api.retrieval import get_query_embedder
from app.web.routes.api.tutorials import get_tutorial_client
from tests.conftest import TEST_PROFESSOR_ID

RECIPE = {
    "id": "exp.analogy_card",
    "name": "Explain with an everyday analogy",
    "summary": "One everyday analogy for the idea, then where the analogy breaks.",
    "renderer": "markdown",
    "prompt": "Explain the subtopic with one everyday analogy, then say where it breaks.",
    "fits": ["concept"],
    "guidance_levels": ["worked", "cue"],
    "inputs": ["subtopic", "chunks"],
    "checks": [],
}
DRAFT = {k: v for k, v in RECIPE.items() if k != "id"} | {"slug": "analogy_card"}


@pytest.fixture
def tutor(client: TestClient) -> Iterator[QueuedClient]:
    fake = QueuedClient()
    client.app.dependency_overrides[get_tutorial_client] = lambda: fake
    client.app.dependency_overrides[get_query_embedder] = FlatEmbedder
    yield fake
    client.app.dependency_overrides.pop(get_tutorial_client)
    client.app.dependency_overrides.pop(get_query_embedder)


def _course(session: Session, name: str = "Mine") -> dict[str, str]:
    course = CourseRow(name=name, subject="intro_python", owner_id=TEST_PROFESSOR_ID)
    session.add(course)
    session.commit()
    return {"X-Course-Id": str(course.id)}


def _subtopic(session: Session, course: dict[str, str]) -> int:
    course_id = int(course["X-Course-Id"])
    docs.chunked_book(session, docs.think_python(), course_id=course_id)
    version = CurriculumVersionRow(label="Intro", course_id=course_id)
    topic = TopicRow(name="Loops", subtopics=[SubtopicRow(name="for loops")])
    version.topics.append(topic)
    session.add(version)
    session.commit()
    return topic.subtopics[0].id


def _yaml(**changes: object) -> str:
    return yaml.safe_dump(RECIPE | changes, sort_keys=False)


def test_create_list_edit_delete_stays_in_its_course(client: TestClient, session: Session) -> None:
    mine, other = _course(session), _course(session, "Other")

    created = client.post("/api/experimental/recipes", json={"yaml": _yaml()}, headers=mine)
    assert created.status_code == 201, created.text
    row = created.json()
    assert (row["recipe_id"], row["renderer"]) == ("exp.analogy_card", "markdown")
    assert client.get("/api/experimental/recipes", headers=other).json() == []

    edited = client.put(
        f"/api/experimental/recipes/{row['id']}",
        json={"yaml": _yaml(name="Analogy, then its limits")},
        headers=mine,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Analogy, then its limits"
    assert client.delete(f"/api/experimental/recipes/{row['id']}", headers=other).status_code == 404

    assert client.delete(f"/api/experimental/recipes/{row['id']}", headers=mine).status_code == 204
    assert client.get("/api/experimental/recipes", headers=mine).json() == []


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"id": "py.analogy"}, "exp."),
        ({"renderer": "markdown", "tool": "python_trace"}, "renderer must be html"),
        ({"checks": ["trace_matches"]}, "trace_matches"),
        ({"fits": []}, "fits"),
    ],
)
def test_invalid_recipes_are_refused_with_the_reason(
    client: TestClient, session: Session, changes: dict, fragment: str
) -> None:
    response = client.post(
        "/api/experimental/recipes", json={"yaml": _yaml(**changes)}, headers=_course(session)
    )
    assert response.status_code == 422, response.text
    assert fragment in response.text


def test_a_duplicate_id_is_refused(client: TestClient, session: Session) -> None:
    mine = _course(session)
    first = client.post("/api/experimental/recipes", json={"yaml": _yaml()}, headers=mine)
    assert first.status_code == 201
    again = client.post("/api/experimental/recipes", json={"yaml": _yaml()}, headers=mine)
    assert again.status_code == 422
    assert "already has a recipe" in again.text


def test_a_draft_is_repaired_once_and_comes_back_as_yaml(
    client: TestClient, session: Session, tutor: QueuedClient
) -> None:
    tutor.replies += [DRAFT | {"tool": "python_trace"}, DRAFT]

    response = client.post(
        "/api/experimental/recipes/draft",
        json={"description": "Teach with an everyday analogy"},
        headers=_course(session),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["problems"] == []
    assert yaml.safe_load(body["yaml"])["id"] == "exp.analogy_card"
    assert body["recipe"]["guidance_levels"] == ["worked", "cue"]
    assert len(tutor.calls) == 2
    assert "renderer must be html" in tutor.calls[1]["prompt"]
    assert "Teach with an everyday analogy" in tutor.calls[0]["prompt"]


def test_a_draft_still_invalid_after_the_retry_returns_its_problems(
    client: TestClient, session: Session, tutor: QueuedClient
) -> None:
    tutor.replies += [DRAFT | {"checks": ["html_loads"]}] * 2
    body = client.post(
        "/api/experimental/recipes/draft",
        json={"description": "anything", "current_yaml": _yaml()},
        headers=_course(session),
    ).json()
    assert body["problems"] == ["the html_loads check needs the html renderer"]
    assert body["recipe"] is None
    assert "The recipe to revise" in tutor.calls[0]["prompt"]


def test_trying_a_recipe_writes_one_block_and_saves_nothing(
    client: TestClient, session: Session, tutor: QueuedClient
) -> None:
    course = _course(session)
    subtopic_id = _subtopic(session, course)
    tutor.replies.append({"markdown": "A for loop is like dealing cards one at a time."})

    response = client.post(
        "/api/experimental/recipes/try",
        json={"yaml": _yaml(), "subtopic_id": subtopic_id, "guidance_level": "worked"},
        headers=course,
    )

    assert response.status_code == 200, response.text
    block = response.json()
    assert block["error"] is None
    assert block["payload"] == {"markdown": "A for loop is like dealing cards one at a time."}
    assert block["chunk_ids"]
    assert "everyday analogy" in tutor.calls[0]["prompt"]
    assert session.scalar(select(func.count()).select_from(TutorialBlockRow)) == 0


def test_the_drafted_id_is_built_from_the_slug_not_trusted(
    client: TestClient, session: Session, tutor: QueuedClient
) -> None:
    tutor.replies.append(DRAFT | {"slug": "exp.One-Analogy card"})
    body = client.post(
        "/api/experimental/recipes/draft",
        json={"description": "anything"},
        headers=_course(session),
    ).json()
    assert body["problems"] == []
    assert yaml.safe_load(body["yaml"])["id"] == "exp.one_analogy_card"
    assert "tool:" not in body["yaml"]


# -- A saved recipe joins the course's recipes ---------------------------------------------------


def _version_of(session: Session, subtopic_id: int) -> int:
    return session.get(SubtopicRow, subtopic_id).topic.curriculum_version_id


def _save(client: TestClient, course: dict[str, str], **changes: object) -> dict:
    response = client.post(
        "/api/experimental/recipes", json={"yaml": _yaml(**changes)}, headers=course
    )
    assert response.status_code == 201, response.text
    return response.json()


def _block(session: Session, subtopic_id: int, status: TutorialBlockStatus) -> TutorialBlockRow:
    block = TutorialBlockRow(
        subtopic_id=subtopic_id,
        recipe_id=RECIPE["id"],
        guidance_level=GuidanceLevel.WORKED,
        renderer=TutorialRenderer.MARKDOWN,
        payload={"markdown": "Like dealing cards."},
        chunk_ids=["chunk-1"],
        status=status,
    )
    session.add(block)
    session.commit()
    return block


def test_a_saved_recipe_is_listed_beside_the_library_in_its_course_only(
    client: TestClient, session: Session
) -> None:
    mine, other = _course(session), _course(session, "Other")
    _save(client, mine)

    ids = [r["id"] for r in client.get("/api/tutorial-recipes", headers=mine).json()["recipes"]]
    assert ids[-1] == RECIPE["id"]
    assert any(i.startswith("py.") for i in ids)
    others = client.get("/api/tutorial-recipes", headers=other).json()["recipes"]
    assert RECIPE["id"] not in [r["id"] for r in others]


def test_a_course_recipe_reaches_students_only_once_approved(
    client: TestClient, session: Session
) -> None:
    course = _course(session)
    version_id = _version_of(session, _subtopic(session, course))
    course_id = int(course["X-Course-Id"])
    _save(client, course)

    def served() -> set[str]:
        return set(servable_recipes(session, "intro_python", course_id, version_id))

    assert RECIPE["id"] not in served()
    assert "py.code_trace_stepper" in served()

    def decide(approved: bool) -> None:
        response = client.put(
            f"/api/tutorial-recipes/{RECIPE['id']}/decision",
            json={"curriculum_version_id": version_id, "approved": approved},
            headers=course,
        )
        assert response.status_code == 200, response.text

    decide(True)
    assert RECIPE["id"] in served()
    decide(False)
    assert RECIPE["id"] not in served()


def test_a_block_of_a_course_recipe_is_written_like_a_library_one(
    client: TestClient, session: Session, tutor: QueuedClient
) -> None:
    course = _course(session)
    subtopic_id = _subtopic(session, course)
    _save(client, course)
    tutor.replies.append({"markdown": "A for loop deals the cards one at a time."})

    response = client.post(
        "/api/tutorial-blocks",
        json={"subtopic_id": subtopic_id, "recipe_id": RECIPE["id"], "guidance_level": "worked"},
        headers=course,
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "draft"
    assert "everyday analogy" in tutor.calls[0]["prompt"]


def test_editing_a_recipe_hides_the_blocks_written_from_its_old_wording(
    client: TestClient, session: Session
) -> None:
    course = _course(session)
    subtopic_id = _subtopic(session, course)
    row = _save(client, course)
    block = _block(session, subtopic_id, TutorialBlockStatus.APPROVED)

    same = client.put(
        f"/api/experimental/recipes/{row['id']}", json={"yaml": row["yaml"]}, headers=course
    )
    assert same.status_code == 200, same.text
    session.refresh(block)
    assert block.status is TutorialBlockStatus.APPROVED

    changed = client.put(
        f"/api/experimental/recipes/{row['id']}",
        json={"yaml": _yaml(prompt="Use a kitchen analogy, then say where it breaks.")},
        headers=course,
    )
    assert changed.status_code == 200, changed.text
    session.refresh(block)
    assert block.status is TutorialBlockStatus.REJECTED


def test_deleting_a_recipe_hides_its_blocks_so_a_reused_id_starts_clean(
    client: TestClient, session: Session
) -> None:
    course = _course(session)
    subtopic_id = _subtopic(session, course)
    row = _save(client, course)
    block = _block(session, subtopic_id, TutorialBlockStatus.DRAFT)

    assert (
        client.delete(f"/api/experimental/recipes/{row['id']}", headers=course).status_code == 204
    )

    session.refresh(block)
    assert block.status is TutorialBlockStatus.REJECTED
