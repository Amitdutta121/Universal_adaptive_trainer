"""Saved course-assistant chats: per course, per professor, saved whole after each run."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _course(client: TestClient, name: str = "Course") -> dict[str, str]:
    response = client.post("/api/courses", json={"name": name})
    assert response.status_code == 201, response.text
    return {"X-Course-Id": str(response.json()["id"])}


def _messages(question: str) -> list[dict]:
    return [
        {"id": "m1", "role": "user", "content": question},
        {"id": "m2", "role": "assistant", "content": "Sure."},
    ]


def test_a_chat_is_saved_listed_reopened_and_deleted(client: TestClient) -> None:
    course = _course(client)
    thread_id = str(uuid.uuid4())

    saved = client.put(
        f"/api/agent/threads/{thread_id}",
        headers=course,
        json={"messages": _messages("Set up   Python\nfor first-years")},
    )
    assert saved.status_code == 200, saved.text
    # The title is the first user message on one line.
    assert saved.json()["title"] == "Set up Python for first-years"

    longer = [*_messages("Set up Python"), {"id": "m3", "role": "user", "content": "More"}]
    client.put(f"/api/agent/threads/{thread_id}", headers=course, json={"messages": longer})

    listed = client.get("/api/agent/threads", headers=course).json()["threads"]
    assert [entry["id"] for entry in listed] == [thread_id]
    reopened = client.get(f"/api/agent/threads/{thread_id}", headers=course).json()
    assert reopened["messages"] == longer

    assert client.delete(f"/api/agent/threads/{thread_id}", headers=course).status_code == 204
    assert client.get("/api/agent/threads", headers=course).json()["threads"] == []
    assert client.get(f"/api/agent/threads/{thread_id}", headers=course).status_code == 404


def test_a_chat_stays_in_its_course(client: TestClient) -> None:
    first, second = _course(client, "First"), _course(client, "Second")
    thread_id = str(uuid.uuid4())
    client.put(f"/api/agent/threads/{thread_id}", headers=first, json={"messages": _messages("x")})

    assert client.get("/api/agent/threads", headers=second).json()["threads"] == []
    assert client.get(f"/api/agent/threads/{thread_id}", headers=second).status_code == 404
    taken = client.put(
        f"/api/agent/threads/{thread_id}", headers=second, json={"messages": _messages("y")}
    )
    assert taken.status_code == 404
    assert client.delete(f"/api/agent/threads/{thread_id}", headers=second).status_code == 404


def test_a_chat_without_a_user_message_is_untitled(client: TestClient) -> None:
    course = _course(client)
    saved = client.put(f"/api/agent/threads/{uuid.uuid4()}", headers=course, json={"messages": []})
    assert saved.json()["title"] == "New chat"
