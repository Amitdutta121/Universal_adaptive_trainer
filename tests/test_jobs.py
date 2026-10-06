"""Background jobs: bulk generation as a job, the Jobs list, restart recovery, judge collection.

Coverage fills as jobs are covered in ``test_coverage.py``; question rounds in
``test_rounds.py``. ``TestClient`` runs submitted work before the request returns, so a
test that POSTs sees the job already finished.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus, JobKind, JudgeBatchStatus, RoundStatus
from app.errors import LLMRequestError
from app.generation.rounds import active_round
from app.jobs.judge_collector import collect_pending_judge_runs
from app.jobs.recovery import INTERRUPTED, fail_interrupted_jobs
from app.jobs.runner import create_job
from app.persistence.models import (
    BackgroundJobRow,
    CourseRow,
    CurriculumVersionRow,
    GenerationRoundRow,
    JudgeBatchRunRow,
    QuestionRow,
    QuestionSetupRow,
)
from app.web.routes.api import questions as api_questions
from tests.conftest import TEST_PROFESSOR_ID
from tests.test_api import _import_taxonomy

BATCH = {"chunks": [{"section_id": 1, "easy": 2, "question_types": ["debugging"]}]}


def _fake_service(*, fail_after: int | None = None) -> type:
    """A GenerationService that stores plain questions and reports each one."""

    class FakeGenerationService:
        def __init__(self, session: Session) -> None:
            self._session = session

        def generate_batch(self, *, on_question: Callable[[], None], run_id: str, **_: object):
            rows = []
            for index in range(2):
                if fail_after is not None and index == fail_after:
                    raise LLMRequestError("The model provider is unavailable.")
                row = QuestionRow(prompt=f"q{index}", original_prompt=f"q{index}")
                self._session.add(row)
                self._session.commit()
                rows.append(row)
                on_question()
            return rows

    return FakeGenerationService


def _job(client: TestClient, job_id: str) -> dict:
    (job,) = [job for job in client.get("/api/jobs").json()["jobs"] if job["id"] == job_id]
    return job


def test_bulk_generation_runs_as_a_job_and_stores_its_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import_taxonomy(client)
    monkeypatch.setattr(api_questions, "GenerationService", _fake_service())

    response = client.post("/api/questions/generate-batch", json=BATCH)

    assert response.status_code == 202, response.text
    job = _job(client, response.json()["job_id"])
    assert (job["kind"], job["status"], job["done"], job["total"]) == (
        "bulk_generation",
        "done",
        2,
        2,
    )
    assert job["title"] == "Bulk generate · 2 questions"
    assert job["result"]["created"] == 2
    assert len(job["result"]["planned"]) == 2
    assert job["link"].startswith("/questions?run_id=")
    assert job["started_at"] and job["finished_at"]


def test_a_failed_bulk_generation_keeps_what_it_made_and_says_why(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import_taxonomy(client)
    monkeypatch.setattr(api_questions, "GenerationService", _fake_service(fail_after=1))

    response = client.post("/api/questions/generate-batch", json=BATCH)

    job = _job(client, response.json()["job_id"])
    assert (job["status"], job["done"], job["total"]) == ("failed", 1, 2)
    assert job["error"] == "The model provider is unavailable."
    assert job["result"] is None
    assert client.get("/api/questions").json()["total"] == 1


def test_a_refused_sheet_is_refused_before_any_job_is_queued(client: TestClient) -> None:
    # No approved taxonomy yet: the fixable problem is reported now, not as a failed job.
    response = client.post("/api/questions/generate-batch", json=BATCH)

    assert response.status_code == 422, response.text
    assert client.get("/api/jobs").json()["jobs"] == []


def _course(session: Session, name: str) -> CourseRow:
    course = CourseRow(name=name, owner_id=TEST_PROFESSOR_ID)
    session.add(course)
    session.commit()
    return course


def test_the_jobs_list_holds_only_the_requested_courses_jobs(
    client: TestClient, session: Session
) -> None:
    mine, other = _course(session, "Mine"), _course(session, "Other")
    for course, title in ((mine, "mine"), (other, "theirs")):
        create_job(
            session,
            kind=JobKind.COVERAGE_FILL,
            title=title,
            total=1,
            request={},
            course_id=course.id,
        )
    session.commit()

    jobs = client.get("/api/jobs", headers={"X-Course-Id": str(mine.id)}).json()["jobs"]

    assert [job["title"] for job in jobs] == ["mine"]


def _round(session: Session, status: RoundStatus) -> GenerationRoundRow:
    version = CurriculumVersionRow(
        label="Jobs v1", status=CurriculumStatus.APPROVED, approved_at=datetime.now(UTC)
    )
    session.add(version)
    session.flush()
    setup = QuestionSetupRow(curriculum_version_id=version.id)
    session.add(setup)
    session.flush()
    row = GenerationRoundRow(setup_id=setup.id, number=1, requested=3, produced=1, status=status)
    session.add(row)
    session.commit()
    return row


def test_a_restart_fails_interrupted_jobs_and_unblocks_the_next_round(
    session: Session, engine
) -> None:
    stuck_round = _round(session, RoundStatus.RUNNING)
    queued_job = create_job(
        session, kind=JobKind.BULK_GENERATION, title="b", total=4, request={}, course_id=None
    )
    finished_job = create_job(
        session, kind=JobKind.BULK_GENERATION, title="c", total=1, request={}, course_id=None
    )
    finished_job.status = RoundStatus.DONE
    session.commit()
    assert active_round(session, stuck_round.setup.curriculum_version_id) is not None

    changed = fail_interrupted_jobs(lambda: Session(engine, expire_on_commit=False))

    assert changed == 2
    session.expire_all()
    assert (stuck_round.status, stuck_round.error) == (RoundStatus.FAILED, INTERRUPTED)
    assert stuck_round.produced == 1
    assert session.get(BackgroundJobRow, queued_job.id).status is RoundStatus.FAILED
    assert session.get(BackgroundJobRow, finished_job.id).status is RoundStatus.DONE
    assert active_round(session, stuck_round.setup.curriculum_version_id) is None


def test_a_question_round_is_listed_as_a_job(client: TestClient, session: Session) -> None:
    row = _round(session, RoundStatus.RUNNING)

    job = _job(client, f"round-{row.id}")

    assert job["kind"] == "question_round"
    assert job["title"] == "Question round 1 · Jobs v1"
    assert (job["status"], job["done"], job["total"]) == ("running", 1, 3)
    assert job["counts"] == {"made": 1, "dropped": 0, "skipped": 0}
    assert job["link"] == f"/review?round={row.id}"


def _judge_run(session: Session, run_id: str, status: JudgeBatchStatus) -> JudgeBatchRunRow:
    row = JudgeBatchRunRow(run_id=run_id, status=status, question_count=4)
    session.add(row)
    session.commit()
    return row


def test_the_collector_polls_every_unfinished_judge_run_and_survives_one_failing(
    session: Session, engine
) -> None:
    _judge_run(session, "aaa", JudgeBatchStatus.SUBMITTED)
    _judge_run(session, "bbb", JudgeBatchStatus.IN_PROGRESS)
    _judge_run(session, "ccc", JudgeBatchStatus.COMPLETED)
    polled: list[str] = []

    def poll(poll_session: Session, run_id: str) -> None:
        polled.append(run_id)
        if run_id == "aaa":
            raise LLMRequestError("provider down")
        run = poll_session.query(JudgeBatchRunRow).filter_by(run_id=run_id).one()
        run.status = JudgeBatchStatus.COMPLETED

    factory = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    assert collect_pending_judge_runs(factory, poll=poll) == 2
    assert sorted(polled) == ["aaa", "bbb"]

    # "bbb" finished; "aaa" is tried again on the next pass.
    polled.clear()
    assert collect_pending_judge_runs(factory, poll=poll) == 1
    assert polled == ["aaa"]


def test_a_second_judge_run_is_refused_while_one_is_running(
    client: TestClient, session: Session
) -> None:
    _judge_run(session, "running", JudgeBatchStatus.IN_PROGRESS)

    response = client.post("/api/evaluation/batch-runs")

    assert response.status_code == 422, response.text
    assert "already in progress" in response.json()["error"]["message"]
    preview = client.get("/api/evaluation/rerun-preview").json()
    assert preview["active_run_id"] == "running"


def test_the_rerun_preview_says_why_judges_cannot_run(client: TestClient) -> None:
    preview = client.get("/api/evaluation/rerun-preview").json()

    assert preview["enabled"] is False
    assert "JUDGE_BATCH_ENABLED" in preview["disabled_reason"]
    assert preview["eligible"] == 0
    assert preview["active_run_id"] is None


def test_a_judge_run_is_listed_as_a_job(client: TestClient, session: Session) -> None:
    run = _judge_run(session, "listed", JudgeBatchStatus.COMPLETED)
    run.completed_count = 3
    run.failed_count = 1
    session.commit()

    job = _job(client, "judge-listed")

    assert (job["kind"], job["status"], job["done"], job["total"]) == ("judge_run", "done", 4, 4)
    assert job["counts"] == {"judged": 3, "failed": 1}


def test_startup_recovers_jobs_left_running(configured_app: FastAPI, session: Session) -> None:
    job = create_job(
        session, kind=JobKind.COVERAGE_FILL, title="x", total=1, request={}, course_id=None
    )
    job.status = RoundStatus.RUNNING
    session.commit()

    with TestClient(configured_app) as http:
        listed = _job(http, f"job-{job.id}")

    assert (listed["status"], listed["error"]) == ("failed", INTERRUPTED)


# --- cancel and retry ---------------------------------------------------------


def _cancelling_service(engine, job_ref: dict, seen: dict) -> type:
    """Makes questions one at a time; the professor cancels right after the first."""

    class CancellingService:
        def __init__(self, session: Session) -> None:
            self._session = session

        def generate_batch(self, *, on_question, start_at: int = 0, **_: object):
            seen.setdefault("start_at", []).append(start_at)
            rows = []
            for index in range(2 - start_at):
                row = QuestionRow(prompt=f"q{index}", original_prompt=f"q{index}")
                self._session.add(row)
                self._session.commit()
                rows.append(row)
                if job_ref.get("cancel_after_first") and index == 0:
                    with Session(engine) as other:  # the cancel arrives on another request
                        job = other.get(BackgroundJobRow, job_ref["id"])
                        job.cancel_requested_at = datetime.now(UTC)
                        other.commit()
                on_question()
            return rows

    return CancellingService


def test_a_cancelled_run_stops_after_its_question_and_a_retry_does_the_rest(
    client: TestClient, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import_taxonomy(client)
    seen: dict = {}
    job_ref = {"cancel_after_first": True, "id": 1}
    monkeypatch.setattr(
        api_questions, "GenerationService", _cancelling_service(engine, job_ref, seen)
    )

    started = client.post("/api/questions/generate-batch", json=BATCH).json()["job_id"]

    job = _job(client, started)
    assert (job["status"], job["done"], job["total"]) == ("cancelled", 1, 2)
    assert job["error"] == "Cancelled. Everything made before it stopped is kept."
    assert job["retry_label"] == "Retry the remaining 1"
    assert job["can_cancel"] is False

    job_ref["cancel_after_first"] = False
    retried = client.post(f"/api/jobs/{started}/retry")

    assert retried.status_code == 202, retried.text
    again = _job(client, retried.json()["job_id"])
    assert (again["status"], again["done"], again["total"]) == ("done", 1, 1)
    assert again["title"] == "Bulk generate · 1 question (retry)"
    assert seen["start_at"] == [0, 1]
    assert client.get("/api/questions").json()["total"] == 2
    # Retried once: offering it again would make the same question twice.
    assert _job(client, started)["retry_label"] is None
    assert client.post(f"/api/jobs/{started}/retry").status_code == 422


def test_cancelling_a_queued_job_ends_it_before_it_starts(
    client: TestClient, session: Session, engine
) -> None:
    from app.jobs.runner import execute

    job = create_job(
        session, kind=JobKind.BULK_GENERATION, title="b", total=3, request={}, course_id=None
    )
    session.commit()

    cancelled = client.post(f"/api/jobs/job-{job.id}/cancel")

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    ran: list[int] = []
    execute(job.id, lambda *_: ran.append(1) or {}, session_factory=lambda: Session(engine))
    assert ran == []


def test_a_running_job_is_asked_to_stop_not_ended(client: TestClient, session: Session) -> None:
    job = create_job(
        session, kind=JobKind.COVERAGE_FILL, title="c", total=3, request={}, course_id=None
    )
    job.status = RoundStatus.RUNNING
    session.commit()

    body = client.post(f"/api/jobs/job-{job.id}/cancel").json()

    assert (body["status"], body["cancel_requested"], body["can_cancel"]) == (
        "running",
        True,
        False,
    )
    again = client.post(f"/api/jobs/job-{job.id}/cancel")
    assert again.status_code == 200  # still running: asking twice is harmless


def test_a_finished_job_cannot_be_cancelled(client: TestClient, session: Session) -> None:
    job = create_job(
        session, kind=JobKind.BULK_GENERATION, title="b", total=1, request={}, course_id=None
    )
    job.status = RoundStatus.DONE
    session.commit()

    response = client.post(f"/api/jobs/job-{job.id}/cancel")

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "This job has already finished."


def test_a_queued_round_can_be_cancelled(client: TestClient, session: Session) -> None:
    row = _round(session, RoundStatus.QUEUED)

    body = client.post(f"/api/jobs/round-{row.id}/cancel").json()

    assert body["status"] == "cancelled"
    assert body["retry_label"] == "Start the next round"
    session.expire_all()
    assert active_round(session, row.setup.curriculum_version_id) is None


def test_a_round_stops_before_its_next_target_when_cancelled(session: Session) -> None:
    from app.jobs.cancel import JobCancelled, raise_if_cancelled

    row = _round(session, RoundStatus.RUNNING)
    raise_if_cancelled(session, row)  # not asked: carries on

    row.cancel_requested_at = datetime.now(UTC)
    session.commit()
    with pytest.raises(JobCancelled):
        raise_if_cancelled(session, row)


def test_a_judge_run_cannot_be_cancelled(client: TestClient, session: Session) -> None:
    _judge_run(session, "busy", JudgeBatchStatus.IN_PROGRESS)

    response = client.post("/api/jobs/judge-busy/cancel")

    assert response.status_code == 422
    assert "can't be stopped" in response.json()["error"]["message"]
    assert _job(client, "judge-busy")["can_cancel"] is False


def test_only_a_failed_judge_run_offers_a_retry(client: TestClient, session: Session) -> None:
    _judge_run(session, "ok", JudgeBatchStatus.COMPLETED)
    _judge_run(session, "lost", JudgeBatchStatus.EXPIRED)

    assert _job(client, "judge-ok")["retry_label"] is None
    assert _job(client, "judge-lost")["retry_label"] == "Run judges again"
    assert client.post("/api/jobs/judge-ok/retry").status_code == 422


def test_a_coverage_retry_targets_what_the_run_did_not_finish() -> None:
    from app.web.routes.api.coverage import coverage_retry_targets

    targets = [
        {"subtopic_id": 1, "difficulty": "easy"},
        {"subtopic_id": 2, "difficulty": "medium"},
        {"subtopic_id": 3, "difficulty": "hard"},
    ]
    stopped = BackgroundJobRow(
        kind=JobKind.COVERAGE_FILL, status=RoundStatus.FAILED, done=1, request={"targets": targets}
    )
    finished = BackgroundJobRow(
        kind=JobKind.COVERAGE_FILL,
        status=RoundStatus.DONE,
        done=3,
        request={"targets": targets},
        result={
            "failed": [{"subtopic_id": 2, "difficulty": "medium", "section_id": 9, "error": "x"}]
        },
    )

    assert [t.subtopic_id for t in coverage_retry_targets(stopped)] == [2, 3]
    assert [(t.subtopic_id, t.difficulty.value) for t in coverage_retry_targets(finished)] == [
        (2, "medium")
    ]


def test_unknown_job_ids_are_not_found(client: TestClient) -> None:
    for job_id in ("job-999", "round-999", "judge-nope", "nonsense", "job-x"):
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 404, job_id


def test_a_job_stored_as_a_bare_sheet_still_retries_from_the_start(
    client: TestClient, session: Session, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Jobs queued before ``start_at`` existed stored the sheet itself as the request."""
    version_id = _import_taxonomy(client)["version"]["id"]
    seen: dict = {}
    monkeypatch.setattr(api_questions, "GenerationService", _cancelling_service(engine, {}, seen))
    old = create_job(
        session,
        kind=JobKind.BULK_GENERATION,
        title="Bulk generate · 2 questions",
        total=2,
        request={**BATCH, "curriculum_version_id": version_id, "seed": None},
        course_id=None,
    )
    old.status = RoundStatus.FAILED
    session.commit()

    retried = client.post(f"/api/jobs/job-{old.id}/retry")

    assert retried.status_code == 202, retried.text
    assert seen["start_at"] == [0]
    assert _job(client, retried.json()["job_id"])["status"] == "done"
