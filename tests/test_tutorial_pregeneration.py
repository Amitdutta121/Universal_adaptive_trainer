"""Approving tutorial blocks by recipe, and the pre-generation job (Phase 6, Task 24)."""

from __future__ import annotations

import book_documents as docs
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_tutorial_generator import QueuedClient
from test_tutorial_routes import tutor  # noqa: F401  (fixture)

from app.domain.enums import GuidanceLevel, TutorialBlockStatus, TutorialRenderer
from app.persistence.models import (
    CurriculumVersionRow,
    SubtopicRow,
    TopicRow,
    TutorialBlockRow,
)


def _taxonomy(session: Session, subtopics: int = 1) -> CurriculumVersionRow:
    docs.chunked_book(session, docs.think_python())
    version = CurriculumVersionRow(label="Intro")
    version.topics.append(
        TopicRow(name="Loops", subtopics=[SubtopicRow(name=f"loops {n}") for n in range(subtopics)])
    )
    session.add(version)
    session.commit()
    return version


def _block(
    session: Session,
    subtopic_id: int,
    recipe_id: str = "py.misconception_line",
    *,
    status: TutorialBlockStatus = TutorialBlockStatus.DRAFT,
    level: GuidanceLevel = GuidanceLevel.CUE,
) -> TutorialBlockRow:
    block = TutorialBlockRow(
        subtopic_id=subtopic_id,
        recipe_id=recipe_id,
        guidance_level=level,
        renderer=TutorialRenderer.MARKDOWN,
        payload={"markdown": "**x**"},
        chunk_ids=["c1"],
        status=status,
    )
    session.add(block)
    session.commit()
    return block


def _decide(client: TestClient, version_id: int, recipe_id: str, approved: bool) -> dict:
    response = client.put(
        f"/api/tutorial-recipes/{recipe_id}/decision",
        json={"curriculum_version_id": version_id, "approved": approved},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _listed(client: TestClient, version_id: int) -> list[int]:
    response = client.get("/api/tutorial-blocks", params={"curriculum_version_id": version_id})
    assert response.status_code == 200, response.text
    return [block["id"] for block in response.json()]


def test_approving_a_recipe_approves_its_blocks(client: TestClient, session: Session) -> None:
    version = _taxonomy(session, subtopics=2)
    first, second = (s.id for s in version.topics[0].subtopics)
    mine = [_block(session, first), _block(session, second)]
    other = _block(session, first, "py.topic_flow")
    failed = _block(session, first, status=TutorialBlockStatus.FAILED)

    body = _decide(client, version.id, "py.misconception_line", True)

    assert body["blocks_changed"] == 2
    for block in [*mine, other, failed]:
        session.refresh(block)
    assert [b.status for b in mine] == [TutorialBlockStatus.APPROVED] * 2
    assert other.status is TutorialBlockStatus.DRAFT
    assert failed.status is TutorialBlockStatus.FAILED
    recipes = client.get(
        "/api/tutorial-recipes", params={"curriculum_version_id": version.id}
    ).json()
    assert recipes["decisions"] == {"py.misconception_line": True}


def test_rejecting_a_recipe_hides_its_blocks(client: TestClient, session: Session) -> None:
    version = _taxonomy(session)
    subtopic_id = version.topics[0].subtopics[0].id
    hidden = _block(session, subtopic_id)
    kept = _block(session, subtopic_id, "py.topic_flow")
    assert set(_listed(client, version.id)) == {hidden.id, kept.id}

    _decide(client, version.id, "py.misconception_line", False)

    session.refresh(hidden)
    assert hidden.status is TutorialBlockStatus.REJECTED
    assert _listed(client, version.id) == [kept.id]
    # Changing one's mind brings them back.
    _decide(client, version.id, "py.misconception_line", True)
    assert set(_listed(client, version.id)) == {hidden.id, kept.id}


def test_a_decision_does_not_reach_another_taxonomy(client: TestClient, session: Session) -> None:
    version = _taxonomy(session)
    other = CurriculumVersionRow(label="Other")
    other.topics.append(TopicRow(name="T", subtopics=[SubtopicRow(name="s")]))
    session.add(other)
    session.commit()
    elsewhere = _block(session, other.topics[0].subtopics[0].id)

    _decide(client, version.id, "py.misconception_line", True)

    session.refresh(elsewhere)
    assert elsewhere.status is TutorialBlockStatus.DRAFT


def test_a_block_made_after_the_decision_starts_decided(
    client: TestClient,
    session: Session,
    tutor: QueuedClient,  # noqa: F811
) -> None:
    version = _taxonomy(session)
    _decide(client, version.id, "py.misconception_line", True)
    tutor.replies.append({"markdown": "**Misconception:** a for loop needs a counter."})
    created = client.post(
        "/api/tutorial-blocks",
        json={
            "subtopic_id": version.topics[0].subtopics[0].id,
            "recipe_id": "py.misconception_line",
            "guidance_level": "cue",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "approved"


def test_an_unknown_recipe_cannot_be_decided(client: TestClient, session: Session) -> None:
    version = _taxonomy(session)
    response = client.put(
        "/api/tutorial-recipes/py.nope/decision",
        json={"curriculum_version_id": version.id, "approved": True},
    )
    assert response.status_code == 404


# --- the pre-generation job ---------------------------------------------------

PREGEN = "/api/tutorial-pregeneration"
MISCONCEPTION = {"markdown": "**Misconception:** a for loop needs a counter."}


def _job(client: TestClient, job_id: str) -> dict:
    (job,) = [job for job in client.get("/api/jobs").json()["jobs"] if job["id"] == job_id]
    return job


def test_a_dry_run_prices_every_missing_block(client: TestClient, session: Session) -> None:
    version = _taxonomy(session, subtopics=2)
    first = version.topics[0].subtopics[0].id
    _block(session, first, level=GuidanceLevel.CUE)

    response = client.post(PREGEN, json={"curriculum_version_id": version.id, "dry_run": True})

    assert response.status_code == 200, response.text
    plan = response.json()
    # 2 subtopics x (stepper: worked, faded + misconception: 3 levels + flow: 3 levels) = 16,
    # minus the cue misconception block already made.
    assert plan["blocks_to_create"] == 15
    assert plan["already_made"] == 1
    assert plan["generation_calls"] == 15
    assert plan["max_attempts_per_block"] == 2
    assert {
        "subtopic_id": first,
        "recipe_id": "py.misconception_line",
        "guidance_level": "cue",
    } not in plan["planned"]
    assert client.get("/api/jobs").json()["jobs"] == []


def test_the_job_reports_progress_and_fills_only_what_is_missing(
    client: TestClient,
    session: Session,
    tutor: QueuedClient,  # noqa: F811
) -> None:
    version = _taxonomy(session)
    tutor.replies.extend([MISCONCEPTION] * 3)
    body = {"curriculum_version_id": version.id, "recipe_ids": ["py.misconception_line"]}

    started = client.post(PREGEN, json=body)

    assert started.status_code == 202, started.text
    job = _job(client, started.json()["job_id"])
    assert job["kind"] == "tutorial_pregeneration"
    assert (job["status"], job["done"], job["total"]) == ("done", 3, 3)
    assert job["counts"] == {"made": 3, "failed": 0, "skipped": 0}
    assert job["link"] == "/tutorials"
    assert len(tutor.calls) == 3
    levels = {
        b["guidance_level"]
        for b in client.get(
            "/api/tutorial-blocks", params={"curriculum_version_id": version.id}
        ).json()
    }
    assert levels == {"worked", "faded", "cue"}
    # Nothing is missing any more: a second run is refused rather than paying again.
    again = client.post(PREGEN, json=body)
    assert again.status_code in (409, 422), again.text


def test_a_subtopic_without_book_text_is_skipped_not_failed(
    client: TestClient,
    session: Session,
    tutor: QueuedClient,  # noqa: F811
) -> None:
    version = CurriculumVersionRow(label="No book")
    version.topics.append(TopicRow(name="T", subtopics=[SubtopicRow(name="s")]))
    session.add(version)
    session.commit()

    started = client.post(
        PREGEN,
        json={"curriculum_version_id": version.id, "recipe_ids": ["py.misconception_line"]},
    )

    job = _job(client, started.json()["job_id"])
    assert job["status"] == "done"
    assert job["counts"] == {"made": 0, "failed": 0, "skipped": 3}
    assert tutor.calls == []


def test_an_unknown_recipe_is_refused_before_queueing(client: TestClient, session: Session) -> None:
    version = _taxonomy(session)
    response = client.post(
        PREGEN, json={"curriculum_version_id": version.id, "recipe_ids": ["py.nope"]}
    )
    assert response.status_code == 404
    assert client.get("/api/jobs").json()["jobs"] == []
