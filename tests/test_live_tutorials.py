"""Live tutorials: no approval step, and missing blocks written on demand (live.py)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_tutorial_generator import QueuedClient
from test_tutorial_pregeneration import MISCONCEPTION, _block
from test_tutorial_routes import tutor  # noqa: F401  (fixture)
from test_tutorial_serving import _course
from test_web_students import _enrol, _start

from app.config import get_settings
from app.domain.enums import GuidanceLevel, JobKind, TutorialBlockStatus
from app.jobs.queue import get_job_queue
from app.persistence.models import BackgroundJobRow, SubtopicRow, TutorialBlockRow

DRAFT = TutorialBlockStatus.DRAFT
FLOW = {"mermaid": 'flowchart TD\n  A["for"] --> B["body"]', "caption": "c"}


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TUTORIALS_LIVE", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class RecordingQueue:
    """Keeps submitted work instead of running it."""

    def __init__(self) -> None:
        self.submitted: list[tuple[Callable[..., None], tuple[Any, ...]]] = []

    def submit(self, func: Callable[..., None], /, *args: Any, **kwargs: Any) -> None:
        self.submitted.append((func, args))


@pytest.fixture
def held(client: TestClient) -> Iterator[RecordingQueue]:
    queue = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: queue
    yield queue
    client.app.dependency_overrides.pop(get_job_queue)


_names = iter(f"Student {n}" for n in range(1000))


def _answer_wrong(client: TestClient, set_id: int) -> dict:
    """A new student's first answer, wrong."""
    run_id = _start(client, _enrol(client, next(_names)), set_id)
    served = client.get(f"/api/training-sessions/{run_id}/next").json()
    answered = client.post(f"/api/attempts/{served['attempt_id']}/answer", json={"answer": "false"})
    assert answered.status_code == 200, answered.text
    return answered.json()


def _live_jobs(session: Session) -> list[BackgroundJobRow]:
    session.expire_all()
    return [
        job
        for job in session.scalars(
            select(BackgroundJobRow).where(BackgroundJobRow.kind == JobKind.TUTORIAL_PREGENERATION)
        )
        if job.request.get("live")
    ]


def test_unreviewed_and_late_blocks_are_served_without_approval(
    client: TestClient, session: Session, live: None, held: RecordingQueue
) -> None:
    set_id, subtopic_id = _course(session, with_blocks=False)
    # Written after the set was published and never approved: live serves it anyway.
    fresh = _block(session, subtopic_id, "py.topic_flow", status=DRAFT, level=GuidanceLevel.WORKED)
    hidden = _block(
        session,
        subtopic_id,
        "py.misconception_line",
        status=TutorialBlockStatus.REJECTED,
        level=GuidanceLevel.WORKED,
    )

    shown = {b["id"] for b in _answer_wrong(client, set_id)["tutorial_blocks"]}

    assert fresh.id in shown
    assert hidden.id not in shown


def test_a_missing_block_is_written_in_the_background_and_served_once_ready(
    client: TestClient,
    session: Session,
    live: None,
    tutor: QueuedClient,  # noqa: F811
) -> None:
    docs.chunked_book(session, docs.think_python())
    set_id, subtopic_id = _course(session, with_blocks=False)
    tutor.replies.extend([MISCONCEPTION, FLOW])
    run_id = _start(client, _enrol(client, next(_names)), set_id)

    served = client.get(f"/api/training-sessions/{run_id}/next").json()

    # A new student's prior is low, so pre-teaching is wanted; the bank is empty, so they
    # get the plain question now and the block is written after the response.
    assert served["preteach_blocks"] == []
    (job,) = _live_jobs(session)
    assert job.status == "done"
    assert job.request["planned"] == [
        {
            "subtopic_id": subtopic_id,
            "recipe_id": "py.misconception_line",
            "guidance_level": "worked",
        }
    ]
    (made,) = session.scalars(select(TutorialBlockRow)).all()
    assert (made.recipe_id, made.status) == ("py.misconception_line", DRAFT)

    answered = client.post(f"/api/attempts/{served['attempt_id']}/answer", json={"answer": "false"})

    # Unreviewed, it is on the result card; the bank still holds fewer than a worked card
    # shows, so the next best-fitting recipe is written too.
    assert [b["id"] for b in answered.json()["tutorial_blocks"]] == [made.id]
    assert [job.request["planned"][0]["recipe_id"] for job in _live_jobs(session)] == [
        "py.misconception_line",
        "py.topic_flow",
    ]
    assert len(tutor.calls) == 2


def test_a_block_asked_for_is_not_asked_for_again(
    client: TestClient, session: Session, live: None, held: RecordingQueue
) -> None:
    set_id, _ = _course(session, with_blocks=False)

    _answer_wrong(client, set_id)
    _answer_wrong(client, set_id)

    # Nothing has been written (the queue holds the jobs), and every moment asked for a
    # different recipe: pre-teaching and the result card, for two students. The course has
    # no video, so the clip recipe is never asked for.
    planned = [job.request["planned"][0]["recipe_id"] for job in _live_jobs(session)]
    assert len(planned) == len(set(planned)) == 3
    assert "py.video_clip" not in planned
    assert len(held.submitted) == 3


def test_a_rejected_recipe_is_never_written(
    client: TestClient, session: Session, live: None, held: RecordingQueue
) -> None:
    set_id, subtopic_id = _course(session, with_blocks=False)
    version = session.get(SubtopicRow, subtopic_id).topic.curriculum_version_id
    decided = client.put(
        "/api/tutorial-recipes/py.misconception_line/decision",
        json={"curriculum_version_id": version, "approved": False},
    )
    assert decided.status_code == 200, decided.text

    _answer_wrong(client, set_id)

    planned = [job.request["planned"][0]["recipe_id"] for job in _live_jobs(session)]
    assert planned
    assert "py.misconception_line" not in planned


def test_the_daily_cap_stops_live_writing(
    client: TestClient,
    session: Session,
    live: None,
    held: RecordingQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUTORIALS_LIVE_DAILY_CAP", "1")
    get_settings.cache_clear()
    set_id, _ = _course(session, with_blocks=False)

    _answer_wrong(client, set_id)
    _answer_wrong(client, set_id)

    assert len(_live_jobs(session)) == 1


def test_a_retired_block_is_no_longer_served(
    client: TestClient, session: Session, live: None, held: RecordingQueue
) -> None:
    set_id, subtopic_id = _course(session, with_blocks=False)
    block = _block(session, subtopic_id, "py.topic_flow", status=DRAFT, level=GuidanceLevel.WORKED)

    retired = client.put(f"/api/tutorial-blocks/{block.id}/retire")

    assert retired.status_code == 200, retired.text
    assert retired.json()["status"] == "rejected"
    assert _answer_wrong(client, set_id)["tutorial_blocks"] == []


def test_a_failed_block_cannot_be_retired(client: TestClient, session: Session) -> None:
    _, subtopic_id = _course(session, with_blocks=False)
    block = _block(session, subtopic_id, status=TutorialBlockStatus.FAILED)

    response = client.put(f"/api/tutorial-blocks/{block.id}/retire")

    assert response.status_code in (409, 422), response.text


def test_with_live_off_nothing_is_written(
    client: TestClient, session: Session, held: RecordingQueue
) -> None:
    set_id, _ = _course(session, with_blocks=False)

    assert _answer_wrong(client, set_id)["tutorial_blocks"] == []
    assert _live_jobs(session) == []
    assert held.submitted == []
