"""Drafting a taxonomy with the AI from the professor's own brief (ADR-052)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.curriculum.drafting import DRAFT_SYSTEM_PROMPT, SIZE_TARGETS, DraftBrief, draft_user_prompt
from app.web.routes.api.curriculum import get_draft_client


class _FakeDrafter:
    """Answers with a fixed proposal, recording what it was told."""

    description = "fake/taxonomy-drafter"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete_structured(self, *, system: str, prompt: str, response_model):
        self.calls.append((system, prompt))
        return response_model.model_validate(
            {
                "analysis": "First-year non-majors; cells before genetics.",
                "label": "Intro Biology",
                "topics": [
                    {
                        "name": "Cells",
                        "description": "What cells are made of.",
                        "subtopics": [
                            {"name": "Cell membranes"},
                            # A near-duplicate the repair step must drop, not reject.
                            {"name": "cell  membranes"},
                            {"name": "Organelles"},
                        ],
                    },
                    # A topic with no subtopics cannot be valid; it is dropped.
                    {"name": "Empty", "subtopics": []},
                ],
            }
        )


@pytest.fixture
def drafter(configured_app: FastAPI) -> _FakeDrafter:
    fake = _FakeDrafter()
    configured_app.dependency_overrides[get_draft_client] = lambda: fake
    return fake


def test_a_draft_is_returned_repaired_and_unsaved(
    client: TestClient, drafter: _FakeDrafter
) -> None:
    response = client.post(
        "/api/curriculum/drafts",
        json={
            "title": "Intro Biology",
            "description": "Cells, genetics and evolution.",
            "audience": "First-year non-majors",
            "must_cover": "Mitosis\nNatural selection",
            "leave_out": "Lab techniques",
            "size": "compact",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["drafted_by"] == "fake/taxonomy-drafter"
    assert body["analysis"].startswith("First-year non-majors")
    topics = body["document"]["topics"]
    assert [topic["name"] for topic in topics] == ["Cells"]
    assert [sub["name"] for sub in topics[0]["subtopics"]] == ["Cell membranes", "Organelles"]

    # The model was told everything the professor wrote, and the size they chose.
    _, prompt = drafter.calls[0]
    for expected in (
        "# Taxonomy title\nIntro Biology",
        "# Audience and level\nFirst-year non-majors",
        "# Must cover\nMitosis\nNatural selection",
        "# Leave out\nLab techniques",
        SIZE_TARGETS["compact"],
    ):
        assert expected in prompt

    # Drafting saves nothing.
    assert client.get("/api/curriculum/versions").json()["total"] == 0


def test_a_draft_needs_a_title_and_a_description(client: TestClient, drafter: _FakeDrafter) -> None:
    assert client.post("/api/curriculum/drafts", json={"title": "X"}).status_code == 422
    assert drafter.calls == []


def test_the_prompt_is_subject_neutral_and_omits_empty_sections() -> None:
    assert "python" not in DRAFT_SYSTEM_PROMPT.lower()
    prompt = draft_user_prompt(DraftBrief(title="Intro Biology", description="Cells."))
    assert "# Audience and level" not in prompt
    assert "# Must cover" not in prompt
    assert prompt.endswith(SIZE_TARGETS["standard"])


def test_the_professors_numbers_are_asked_for_and_retried_once_when_missed(
    client: TestClient, drafter: _FakeDrafter
) -> None:
    # The fake always answers 1 topic with 2 subtopics after repair.
    response = client.post(
        "/api/curriculum/drafts",
        json={
            "title": "Intro Biology",
            "description": "Cells.",
            "size": "detailed",
            "topic_count": 3,
            "subtopic_count": 9,
        },
    )
    assert response.status_code == 200, response.text
    # The numbers replace the preset, and a miss is named in one retry.
    first, second = (prompt for _, prompt in drafter.calls)
    assert "# Size\nExactly 3 topics and exactly 9 subtopics in all." in first
    assert "45 subtopics" not in first
    assert "Your last draft had 1 topics instead of 3 and 2 subtopics instead of 9." in second
    # The second answer is returned as it is: the builder is where counts get fixed by hand.
    assert len(response.json()["document"]["topics"]) == 1


def test_a_draft_that_matches_the_numbers_is_not_retried(
    client: TestClient, drafter: _FakeDrafter
) -> None:
    response = client.post(
        "/api/curriculum/drafts",
        json={"title": "Bio", "description": "Cells.", "topic_count": 1, "subtopic_count": 2},
    )
    assert response.status_code == 200, response.text
    assert len(drafter.calls) == 1


def test_fewer_subtopics_than_topics_is_refused(client: TestClient, drafter: _FakeDrafter) -> None:
    response = client.post(
        "/api/curriculum/drafts",
        json={"title": "Bio", "description": "Cells.", "topic_count": 5, "subtopic_count": 3},
    )
    assert response.status_code == 422
    assert drafter.calls == []


def test_one_number_alone_shapes_the_size_line() -> None:
    from app.curriculum.drafting import DraftBrief, size_target

    assert size_target(DraftBrief(title="t", description="d", topic_count=4)) == (
        "Exactly 4 topics, with 2 to 5 subtopics each."
    )
    assert size_target(DraftBrief(title="t", description="d", subtopic_count=12)) == (
        "Exactly 12 subtopics in all, grouped into topics of 2 to 5 subtopics."
    )
    assert "about 30 subtopics" in size_target(DraftBrief(title="t", description="d"))


def test_out_of_scope_parts_come_back_with_the_draft(client: TestClient, drafter) -> None:
    original = drafter.complete_structured

    def with_out_of_scope(**kwargs):
        result = original(**kwargs)
        return result.model_copy(update={"out_of_scope": ["Lab safety demo", "  "]})

    drafter.complete_structured = with_out_of_scope
    response = client.post(
        "/api/curriculum/drafts", json={"title": "Intro Biology", "description": "Cells."}
    )
    assert response.status_code == 200, response.text
    assert response.json()["out_of_scope"] == ["Lab safety demo"]
