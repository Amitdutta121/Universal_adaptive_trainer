"""Question setup routes: styles, suggest, save (starts round 1), current (agent A)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llm_fakes import RaisingJudgeClient
from sqlalchemy.orm import Session
from test_styles import FakeSuggester, make_taxonomy

from app.domain.enums import CurriculumStatus, RoundStatus
from app.errors import LLMRequestError
from app.generation import rounds
from app.persistence.models import CourseRow, GenerationRoundRow, QuestionSetupRow
from app.persistence.repositories import GenerationRoundRepository
from app.web.routes.api.setup import get_setup_client
from tests.conftest import TEST_PROFESSOR_ID


@pytest.fixture
def http(configured_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(configured_app) as test_client:
        yield test_client


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Stand-ins for agent B's round pipeline: record the calls, create a queued round."""
    calls: dict[str, list[Any]] = {"start": [], "run": []}

    def start_round(session: Session, setup_id: int, *, size: int = 10) -> GenerationRoundRow:
        calls["start"].append((setup_id, size))
        return GenerationRoundRepository(session).add(
            GenerationRoundRow(setup_id=setup_id, number=1, requested=size)
        )

    monkeypatch.setattr(rounds, "start_round", start_round)
    monkeypatch.setattr(rounds, "run_round", lambda round_id: calls["run"].append(round_id))
    return calls


def _body(version_id: int, subtopic_id: int, styles: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "curriculum_version_id": version_id,
        "approved_styles": [{"subtopic_id": subtopic_id, "style_ids": styles}],
        "cell_targets": [
            {"subtopic_id": subtopic_id, "difficulty": d, "target": 3}
            for d in ("easy", "medium", "hard")
        ],
        **extra,
    }


def test_styles_lists_the_course_subject_library(http: TestClient, session: Session) -> None:
    response = http.get("/api/styles")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subject"] == "intro_python"
    assert len(body["styles"]) == 10
    assert len(body["styles"][0]["examples"]) == 2

    course = CourseRow(name="Mechanics", subject="physics", owner_id=TEST_PROFESSOR_ID)
    session.add(course)
    session.commit()
    scoped = http.get("/api/styles", headers={"X-Course-Id": str(course.id)}).json()
    assert scoped == {"subject": "physics", "styles": []}
    assert len(http.get("/api/styles?subject=intro_python").json()["styles"]) == 10


def test_suggest_returns_the_validated_suggestion(
    configured_app: FastAPI, http: TestClient, session: Session
) -> None:
    version, subtopics = make_taxonomy(session)
    fake = FakeSuggester(
        {
            "subtopics": [
                {
                    "subtopic_id": subtopics[0].id,
                    "style_ids": ["py.bogus"],
                    "reason": "r",
                    "easy": 9,
                }
            ]
        }
    )
    configured_app.dependency_overrides[get_setup_client] = lambda: fake

    response = http.post("/api/setup/suggest", json={"curriculum_version_id": version.id})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["curriculum_version_id"] == version.id
    assert len(body["subtopics"]) == 3 and len(body["cell_targets"]) == 9
    assert all(s["style_ids"] and "py.bogus" not in s["style_ids"] for s in body["subtopics"])
    assert {"subtopic_id": subtopics[0].id, "difficulty": "easy", "target": 6} in body[
        "cell_targets"
    ]
    # Nothing persisted.
    assert session.query(QuestionSetupRow).count() == 0


def test_suggest_errors_map_to_api_errors(
    configured_app: FastAPI, http: TestClient, session: Session
) -> None:
    proposed, _ = make_taxonomy(session, status=CurriculumStatus.PROPOSED)
    approved, _ = make_taxonomy(session)
    configured_app.dependency_overrides[get_setup_client] = lambda: RaisingJudgeClient(
        LLMRequestError("The LLM provider returned HTTP 500.")
    )

    assert http.post("/api/setup/suggest", json={"curriculum_version_id": 999}).status_code == 404
    refused = http.post("/api/setup/suggest", json={"curriculum_version_id": proposed.id})
    assert refused.status_code == 422, refused.text
    failed = http.post("/api/setup/suggest", json={"curriculum_version_id": approved.id})
    assert failed.status_code == 502, failed.text
    assert "error" in failed.json()


def test_suggest_without_a_configured_model_says_so(
    http: TestClient, session: Session
) -> None:
    version, _ = make_taxonomy(session)
    response = http.post("/api/setup/suggest", json={"curriculum_version_id": version.id})
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "configuration_error"


def test_save_persists_starts_round_one_and_schedules_it(
    http: TestClient, session: Session, started: dict[str, list[Any]]
) -> None:
    version, subtopics = make_taxonomy(session)
    assert http.get(f"/api/setup?curriculum_version_id={version.id}").json() == {"setup": None}

    response = http.post(
        "/api/setup",
        json=_body(version.id, subtopics[0].id, ["py.trace_steps", "py.trace_steps"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert started["start"] == [(body["setup_id"], 10)]
    assert started["run"] == [body["round_id"]]
    session.expire_all()
    row = session.get(QuestionSetupRow, body["setup_id"])
    assert row.approved_styles == {str(subtopics[0].id): ["py.trace_steps"]}
    assert len(row.cell_targets) == 3

    current = http.get(f"/api/setup?curriculum_version_id={version.id}").json()["setup"]
    assert current["id"] == body["setup_id"]
    assert current["approved_styles"] == [
        {"subtopic_id": subtopics[0].id, "style_ids": ["py.trace_steps"]}
    ]
    assert current["latest_round"]["id"] == body["round_id"]
    assert current["latest_round"]["status"] == RoundStatus.QUEUED.value


def test_save_passes_the_round_size(
    http: TestClient, session: Session, started: dict[str, list[Any]]
) -> None:
    version, subtopics = make_taxonomy(session)
    body = _body(version.id, subtopics[0].id, ["py.concept_check"], round_size=4)
    assert http.post("/api/setup", json=body).status_code == 201
    assert started["start"][0][1] == 4


@pytest.mark.parametrize(
    "case",
    ["unknown_style", "foreign_subtopic", "no_styles", "duplicate_cell", "unapproved"],
)
def test_save_refuses_an_invalid_setup(
    http: TestClient, session: Session, started: dict[str, list[Any]], case: str
) -> None:
    status = CurriculumStatus.PROPOSED if case == "unapproved" else CurriculumStatus.APPROVED
    version, subtopics = make_taxonomy(session, status=status)
    body = _body(version.id, subtopics[0].id, ["py.trace_steps"])
    if case == "unknown_style":
        body["approved_styles"][0]["style_ids"] = ["py.nope"]
    elif case == "foreign_subtopic":
        body["approved_styles"][0]["subtopic_id"] = 999_999
    elif case == "no_styles":
        body["approved_styles"][0]["style_ids"] = []
    elif case == "duplicate_cell":
        body["cell_targets"].append(body["cell_targets"][0])

    response = http.post("/api/setup", json=body)

    assert response.status_code == 422, response.text
    assert started["start"] == [] and started["run"] == []
    assert session.query(QuestionSetupRow).count() == 0


def test_save_rolls_back_when_the_round_cannot_start(
    http: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.errors import DomainRuleError

    def refuse(*_: Any, **__: Any) -> GenerationRoundRow:
        raise DomainRuleError("The setup already has a round.")

    monkeypatch.setattr(rounds, "start_round", refuse)
    version, subtopics = make_taxonomy(session)

    response = http.post("/api/setup", json=_body(version.id, subtopics[0].id, ["py.fix_one_bug"]))

    assert response.status_code == 422, response.text
    assert session.query(QuestionSetupRow).count() == 0


def test_setup_routes_stay_inside_the_course(
    http: TestClient, session: Session, started: dict[str, list[Any]]
) -> None:
    version, subtopics = make_taxonomy(
        session, course=CourseRow(name="A", subject="intro_python", owner_id=TEST_PROFESSOR_ID)
    )
    other = CourseRow(name="B", subject="intro_python", owner_id=TEST_PROFESSOR_ID)
    session.add(other)
    session.commit()
    headers = {"X-Course-Id": str(other.id)}

    assert (
        http.get(f"/api/setup?curriculum_version_id={version.id}", headers=headers).status_code
        == 404
    )
    body = _body(version.id, subtopics[0].id, ["py.trace_steps"])
    assert http.post("/api/setup", json=body, headers=headers).status_code == 404
    assert started["start"] == []
