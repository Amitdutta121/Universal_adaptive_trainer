"""``POST /api/generation-runs`` (ADR-066): every kind of professor generation run.

Each old route's scenarios are rerun here through the new endpoint. ``TestClient`` runs
queued work before the request returns, so a test that POSTs sees the job finished.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.persistence.models import BackgroundJobRow, QuestionRow
from app.web.routes.api import questions as api_questions
from tests.test_api import _import_chunked_book, _import_taxonomy

RUNS = "/api/generation-runs"

SHEET = {
    "kind": "chunks",
    "chunks": [{"chunk_id": "a" * 32, "easy": 2, "question_types": ["debugging"]}],
}


def _job(client: TestClient, job_id: str) -> dict:
    (job,) = [job for job in client.get("/api/jobs").json()["jobs"] if job["id"] == job_id]
    return job


def _recording_service(seen: dict) -> type:
    """A GenerationService that stores one plain question per planned question."""

    class FakeGenerationService:
        def __init__(self, session: Session) -> None:
            self._session = session

        def generate_batch(self, *, on_question: Callable[[], None], **kwargs: object):
            seen.update(kwargs)
            rows = []
            for chunk in kwargs["chunks"]:
                for _ in range(chunk.total):
                    row = QuestionRow(prompt="q", original_prompt="q")
                    self._session.add(row)
                    self._session.commit()
                    rows.append(row)
                    on_question()
            return rows

    return FakeGenerationService


class _NoModel:
    """Fails the test if a dry run reaches the generator."""

    def __init__(self, *_: object, **__: object) -> None:
        raise AssertionError("a dry run built a GenerationService")


# ------------------------------------------------------------------ chunks


def test_a_chunk_sheet_runs_as_a_bulk_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _import_taxonomy(client)
    seen: dict = {}
    monkeypatch.setattr(api_questions, "GenerationService", _recording_service(seen))

    response = client.post(RUNS, json={"target": SHEET})

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["kind"] == "chunks" and body["round_id"] is None
    job = _job(client, body["job_id"])
    assert (job["kind"], job["status"], job["done"], job["total"]) == (
        "bulk_generation",
        "done",
        2,
        2,
    )
    assert job["result"]["created"] == 2
    assert job["link"].startswith("/questions?run_id=")


def test_one_type_and_difficulty_per_chunk_is_the_old_single_generation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``/questions/generate`` was one question per chunk, one type, one difficulty."""
    _import_taxonomy(client)
    seen: dict = {}
    monkeypatch.setattr(api_questions, "GenerationService", _recording_service(seen))
    chunk = {"medium": 1, "question_types": ["debugging"]}

    response = client.post(
        RUNS,
        json={
            "target": {
                "kind": "chunks",
                "chunks": [{"chunk_id": "a" * 32, **chunk}, {"chunk_id": "b" * 32, **chunk}],
                "seed": "s1",
            }
        },
    )

    assert response.status_code == 202, response.text
    assert [c.chunk_id for c in seen["chunks"]] == ["a" * 32, "b" * 32]
    assert all(c.total == 1 for c in seen["chunks"])
    assert seen["seed"] == "s1"


def test_a_whole_book_expands_to_every_chunk_of_its_current_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    book, chunks = _import_chunked_book(client)
    _import_taxonomy(client)
    seen: dict = {}
    monkeypatch.setattr(api_questions, "GenerationService", _recording_service(seen))

    response = client.post(
        RUNS,
        json={
            "target": {
                "kind": "chunks",
                "whole_book": {"book_id": book["id"], "easy": 1, "question_types": ["debugging"]},
            }
        },
    )

    assert response.status_code == 202, response.text
    assert [c.chunk_id for c in seen["chunks"]] == [c["id"] for c in chunks]
    assert _job(client, response.json()["job_id"])["total"] == len(chunks)


def test_a_chunk_run_uses_the_active_curriculum_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _import_taxonomy(client)["version"]["id"]
    _import_taxonomy(client)
    assert client.post(f"/api/curriculum/versions/{old}/activate").status_code == 200
    seen: dict = {}
    monkeypatch.setattr(api_questions, "GenerationService", _recording_service(seen))

    response = client.post(RUNS, json={"target": SHEET})

    assert response.status_code == 202, response.text
    assert seen["curriculum_version_id"] == old


def test_a_chunk_run_without_an_approved_curriculum_is_refused_before_queueing(
    client: TestClient,
) -> None:
    response = client.post(RUNS, json={"target": SHEET})

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_question_spec"
    assert client.get("/api/jobs").json()["jobs"] == []


@pytest.mark.parametrize(
    "target",
    [
        {"kind": "chunks"},
        {"kind": "chunks", "chunks": SHEET["chunks"], "whole_book": {"book_id": 1}},
        {"kind": "chunks", "chunks": [{"chunk_id": "c", "easy": 1, "question_types": ["essay"]}]},
        {"kind": "nonsense"},
    ],
    ids=["no-selection", "two-selections", "unknown-type", "unknown-kind"],
)
def test_a_malformed_target_is_a_422(client: TestClient, target: dict) -> None:
    response = client.post(RUNS, json={"target": target})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_chunk_dry_run_prices_the_sheet_without_a_model_call_or_a_row(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_questions, "GenerationService", _NoModel)
    sheet = {
        "kind": "chunks",
        "chunks": [
            {"chunk_id": "c1", "easy": 1, "hard": 2, "question_types": ["coding", "debugging"]}
        ],
    }

    response = client.post(RUNS, json={"target": sheet, "dry_run": True})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "chunks"
    # The same numbers /questions/batch-plan gives for this sheet.
    assert body["totals"] == {
        "questions_to_create": 6,
        "generation_calls": 6,
        "judge_calls": 24,
        "max_attempts_per_question": 3,
        "identical_repeats": 2,
    }
    assert [q["question_type"] for q in body["planned"]][:2] == ["coding", "debugging"]
    assert session.query(QuestionRow).count() == 0
    assert session.query(BackgroundJobRow).count() == 0


# ------------------------------------------------------------------ gaps
# The run scenarios are in test_coverage.py, whose ``_run`` posts here.


def test_a_gap_dry_run_plans_one_mcq_per_gap_without_retrieving(
    configured_app, session: Session
) -> None:
    from app.web.routes.api.retrieval import get_query_embedder

    def no_embedder():
        raise AssertionError("a dry run built the query embedder")

    configured_app.dependency_overrides[get_query_embedder] = no_embedder
    gaps = [{"subtopic_id": 1, "difficulty": "easy"}, {"subtopic_id": 2, "difficulty": "hard"}]
    with TestClient(configured_app) as http:
        response = http.post(
            RUNS, json={"target": {"kind": "gaps", "targets": gaps}, "dry_run": True}
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(q["subtopic_id"], q["difficulty"], q["question_type"]) for q in body["planned"]] == [
        (1, "easy", "multiple_choice"),
        (2, "hard", "multiple_choice"),
    ]
    assert body["totals"]["questions_to_create"] == 2
    assert body["totals"]["judge_calls"] == 8
    assert session.query(QuestionRow).count() == 0
    assert session.query(BackgroundJobRow).count() == 0


# ------------------------------------------------------------------ regenerate


@pytest.fixture
def source(client: TestClient, session: Session, settings, monkeypatch: pytest.MonkeyPatch):
    """A real generated question, and the job's GenerationService wired to a fake model."""
    from llm_fakes import MetricJudgeClient
    from test_generation_base import _debugging_draft, _seed

    from app.domain.enums import Difficulty, QuestionType
    from app.generation.service import GenerationService

    _version, topic, subtopic, chunk_ids = _seed(session, settings)
    fake = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))
    (row,) = GenerationService(session, client=fake).generate_for_chunks(
        curriculum_version_id=_version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_chunk_ids=[chunk_ids[0]],
    )
    monkeypatch.setattr(
        api_questions, "GenerationService", lambda s: GenerationService(s, client=fake)
    )
    row.fake = fake
    return row


def _regenerate(question_id: int, feedback: str = "Make the distractors subtler.", **extra):
    return {
        "target": {"kind": "regenerate", "question_id": question_id, "feedback": feedback},
        **extra,
    }


def test_a_regeneration_runs_as_a_job_and_returns_both_ids(
    client: TestClient, session: Session, source
) -> None:
    response = client.post(RUNS, json=_regenerate(source.id))

    assert response.status_code == 202, response.text
    job = _job(client, response.json()["job_id"])
    assert (job["kind"], job["status"], job["done"], job["total"]) == (
        "regeneration",
        "done",
        1,
        1,
    )
    result = job["result"]
    assert result["regenerated_from_question_id"] == source.id
    assert result["question_id"] == result["question"]["id"] != source.id
    assert "Make the distractors subtler." in source.fake.generation_calls[-1]["prompt"]
    # Grouped under the job's run, so the job's link finds the new question.
    listed = client.get(job["link"].replace("/questions", "/api/questions")).json()
    assert [q["id"] for q in listed["questions"]] == [result["question_id"]]
    assert job["retry_label"] is None


def test_regenerating_an_unknown_question_is_a_404_before_queueing(client: TestClient) -> None:
    response = client.post(RUNS, json=_regenerate(424242))

    assert response.status_code == 404
    assert client.get("/api/jobs").json()["jobs"] == []


def test_a_regeneration_needs_feedback(client: TestClient) -> None:
    assert client.post(RUNS, json=_regenerate(1, feedback="")).status_code == 422


def test_a_superseded_source_curriculum_is_refused_before_queueing(
    client: TestClient, session: Session, source
) -> None:
    from app.domain.enums import CurriculumStatus
    from app.persistence.models import CurriculumVersionRow

    session.get(
        CurriculumVersionRow, source.curriculum_version_id
    ).status = CurriculumStatus.SUPERSEDED
    session.commit()

    response = client.post(RUNS, json=_regenerate(source.id))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_question_spec"
    assert client.get("/api/jobs").json()["jobs"] == []


def test_a_regeneration_dry_run_plans_one_question_without_a_call_or_a_row(
    client: TestClient, session: Session, source
) -> None:
    calls_before = len(source.fake.generation_calls)
    rows_before = session.query(QuestionRow).count()

    response = client.post(RUNS, json=_regenerate(source.id, dry_run=True))

    assert response.status_code == 200, response.text
    body = response.json()
    (planned,) = body["planned"]
    assert planned["question_id"] == source.id
    assert planned["chunk_id"] == source.spec["source_chunk_ids"][0]
    assert (planned["difficulty"], planned["question_type"]) == ("medium", "debugging")
    assert body["totals"]["questions_to_create"] == 1
    assert len(source.fake.generation_calls) == calls_before
    assert session.query(QuestionRow).count() == rows_before
    assert session.query(BackgroundJobRow).count() == 0
