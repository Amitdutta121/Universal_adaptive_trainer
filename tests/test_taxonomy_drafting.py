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
