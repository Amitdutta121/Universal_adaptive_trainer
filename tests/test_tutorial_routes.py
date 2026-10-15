"""The tutorial recipe and block routes (Phase 5)."""

from __future__ import annotations

from collections.abc import Iterator

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_tutorial_generator import QueuedClient

from app.persistence.models import CurriculumVersionRow, SubtopicRow, TopicRow
from app.web.routes.api.retrieval import get_query_embedder
from app.web.routes.api.tutorials import get_tutorial_client


class FlatEmbedder:
    """Every text gets the same vector, so every chunk ranks equally."""

    model = "fake/flat"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def tutor(client: TestClient) -> Iterator[QueuedClient]:
    fake = QueuedClient()
    client.app.dependency_overrides[get_tutorial_client] = lambda: fake
    client.app.dependency_overrides[get_query_embedder] = FlatEmbedder
    yield fake
    client.app.dependency_overrides.pop(get_tutorial_client)
    client.app.dependency_overrides.pop(get_query_embedder)


def _subtopic(session: Session) -> int:
    docs.chunked_book(session, docs.think_python())
    version = CurriculumVersionRow(label="Intro")
    topic = TopicRow(name="Loops", subtopics=[SubtopicRow(name="for loops")])
    version.topics.append(topic)
    session.add(version)
    session.commit()
    return topic.subtopics[0].id


def test_recipes_are_listed_for_the_subject(client: TestClient) -> None:
    body = client.get("/api/tutorial-recipes").json()
    assert body["subject"] == "intro_python"
    assert {recipe["id"] for recipe in body["recipes"]} == {
        "py.code_trace_stepper",
        "py.topic_flow",
        "py.misconception_line",
    }


def test_generate_then_list_blocks(
    client: TestClient, session: Session, tutor: QueuedClient
) -> None:
    subtopic_id = _subtopic(session)
    tutor.replies.append({"markdown": "**Misconception:** a for loop needs a counter."})
    created = client.post(
        "/api/tutorial-blocks",
        json={
            "subtopic_id": subtopic_id,
            "recipe_id": "py.misconception_line",
            "guidance_level": "cue",
        },
    )
    assert created.status_code == 201, created.text
    block = created.json()
    assert block["status"] == "draft"
    assert block["renderer"] == "markdown"
    assert block["chunk_ids"]
    listed = client.get("/api/tutorial-blocks", params={"subtopic_id": subtopic_id}).json()
    assert [item["id"] for item in listed] == [block["id"]]


def test_a_level_the_recipe_lacks_is_refused(
    client: TestClient, session: Session, tutor: QueuedClient
) -> None:
    response = client.post(
        "/api/tutorial-blocks",
        json={
            "subtopic_id": _subtopic(session),
            "recipe_id": "py.code_trace_stepper",
            "guidance_level": "cue",
        },
    )
    assert response.status_code in (400, 409, 422), response.text
    assert tutor.calls == []
