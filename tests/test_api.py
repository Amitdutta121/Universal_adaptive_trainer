"""The JSON API, over real HTTP.

Covers the shape of every endpoint that mirrors an existing professor
capability, plus the two invariants that matter to a client: errors always come
back as JSON under ``/api``, and an invalid upload changes nothing.
"""

from __future__ import annotations

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus, ReviewDecision
from app.persistence.repositories import BookRepository, CurriculumRepository

VALID_TAXONOMY = (
    b'{"schema_version":"1","label":"Uploaded","topics":['
    b'{"name":"Loops","subtopics":[{"name":"While loops"},{"name":"For loops"}]}]}'
)


def _import_book(client: TestClient) -> dict:
    response = client.post(
        "/api/books",
        files={
            "file": ("think_python.json", docs.to_bytes(docs.think_python()), "application/json")
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _import_taxonomy(client: TestClient) -> dict:
    response = client.post(
        "/api/curriculum/versions",
        files={"file": ("taxonomy.json", VALID_TAXONOMY, "application/json")},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------------- system


def test_health_reports_a_real_database_probe(client: TestClient) -> None:
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["database_ok"] is True
    assert payload["llm_configured"] is False


def test_config_publishes_every_enum_a_client_would_hard_code(client: TestClient) -> None:
    payload = client.get("/api/config").json()

    assert payload["supported_book_extensions"] == [".json"]
    assert [option["value"] for option in payload["difficulties"]] == ["easy", "medium", "hard"]
    assert {option["value"] for option in payload["question_types"]} == {
        "multiple_choice",
        "true_false",
        "output_prediction",
        "code_completion",
        "debugging",
        "parsons",
        "coding",
    }
    assert {option["value"] for option in payload["generators"]} == {"base", "personalized"}
    # Rejection reasons carry the professor-facing label, not the raw code.
    labels = {option["value"]: option["label"] for option in payload["rejection_reasons"]}
    assert labels["too_easy"] != "too_easy"


def test_counts_start_at_zero(client: TestClient) -> None:
    payload = client.get("/api/counts").json()
    assert payload == {
        "books": 0,
        "curriculum_versions": 0,
        "questions": 0,
        "reviews": 0,
        "preferences": 0,
        "students": 0,
    }


# -------------------------------------------------------------------------- books


def test_book_list_is_empty_before_any_import(client: TestClient) -> None:
    assert client.get("/api/books").json() == {"books": [], "total": 0}


def test_import_book_returns_the_created_book(client: TestClient, session: Session) -> None:
    book = _import_book(client)

    assert book["title"] == "Think Python"
    assert book["status"] == "imported"
    assert book["source_format"] == "book_json"
    assert BookRepository(session).count() == 1


def test_book_detail_exposes_the_chapter_section_hierarchy(client: TestClient) -> None:
    book_id = _import_book(client)["id"]

    payload = client.get(f"/api/books/{book_id}").json()

    assert payload["book"]["id"] == book_id
    assert payload["section_count"] > 0
    assert payload["chapters"]
    first_section = payload["chapters"][0]["sections"][0]
    assert first_section["display_title"]
    assert "text" not in first_section  # summaries stay light


def test_section_detail_carries_verbatim_text_and_a_citation(client: TestClient) -> None:
    book_id = _import_book(client)["id"]
    sections = client.get(f"/api/books/{book_id}/sections").json()["sections"]
    section_id = sections[0]["id"]

    payload = client.get(f"/api/books/{book_id}/sections/{section_id}").json()

    assert payload["text"]
    assert payload["citation"]
    assert payload["source"]["book_title"] == "Think Python"
    assert payload["section"]["id"] == section_id


def test_section_under_the_wrong_book_is_a_404(client: TestClient) -> None:
    book_id = _import_book(client)["id"]
    section_id = client.get(f"/api/books/{book_id}/sections").json()["sections"][0]["id"]

    response = client.get(f"/api/books/{book_id + 999}/sections/{section_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_invalid_book_document_is_rejected_and_stores_nothing(
    client: TestClient, session: Session
) -> None:
    response = client.post(
        "/api/books",
        files={"file": ("broken.json", b'{"schema_version":"1"}', "application/json")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_book_document"
    assert BookRepository(session).count() == 0


def test_unsupported_book_extension_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/books", files={"file": ("book.pdf", b"%PDF-1.4", "application/pdf")}
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file"


# --------------------------------------------------------------------- curriculum


def test_approved_curriculum_is_404_before_any_upload(client: TestClient) -> None:
    response = client.get("/api/curriculum/approved")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_taxonomy_upload_creates_an_approved_version(client: TestClient, session: Session) -> None:
    payload = _import_taxonomy(client)

    assert payload["version"]["status"] == "approved"
    assert payload["version"]["generated_by"] == "taxonomy-upload"
    assert payload["topic_count"] == 1
    assert payload["subtopic_count"] == 2
    assert [topic["name"] for topic in payload["topics"]] == ["Loops"]
    assert [item["name"] for item in payload["topics"][0]["subtopics"]] == [
        "While loops",
        "For loops",
    ]
    stored = CurriculumRepository(session).get_latest()
    assert stored is not None
    assert stored.status == CurriculumStatus.APPROVED


def test_version_list_names_the_approved_version(client: TestClient) -> None:
    created = _import_taxonomy(client)["version"]["id"]

    payload = client.get("/api/curriculum/versions").json()

    assert payload["total"] == 1
    assert payload["approved_version_id"] == created
    assert payload["latest_version_id"] == created


def test_approved_curriculum_matches_the_uploaded_version(client: TestClient) -> None:
    created = _import_taxonomy(client)["version"]["id"]

    assert client.get("/api/curriculum/approved").json()["version"]["id"] == created


def test_subtopic_detail_reports_a_taxonomy_upload_has_no_evidence(client: TestClient) -> None:
    version = _import_taxonomy(client)
    subtopic_id = version["topics"][0]["subtopics"][0]["id"]

    payload = client.get(f"/api/curriculum/subtopics/{subtopic_id}").json()

    assert payload["subtopic"]["name"] == "While loops"
    assert payload["topic"]["name"] == "Loops"
    assert payload["is_taxonomy_upload"] is True
    assert payload["evidence"] == []
    assert payload["book_count"] == 0


def test_invalid_taxonomy_is_rejected_and_stores_nothing(
    client: TestClient, session: Session
) -> None:
    response = client.post(
        "/api/curriculum/versions",
        files={
            "file": ("taxonomy.json", b'{"schema_version":"1","topics":[]}', "application/json")
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_taxonomy_document"
    assert CurriculumRepository(session).count() == 0


# ---------------------------------------------------------------------- questions


def test_question_list_is_empty_before_any_generation(client: TestClient) -> None:
    assert client.get("/api/questions").json() == {
        "questions": [],
        "status_counts": {},
        "total": 0,
    }


def test_generation_without_an_approved_curriculum_is_refused(client: TestClient) -> None:
    book_id = _import_book(client)["id"]
    section_id = client.get(f"/api/books/{book_id}/sections").json()["sections"][0]["id"]

    response = client.post(
        "/api/questions/generate",
        json={
            "topic_id": 1,
            "subtopic_id": 1,
            "question_type": "debugging",
            "difficulty": "medium",
            "book_id": book_id,
            "section_ids": [section_id],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_question_spec"


def test_generation_requires_a_source_selection(client: TestClient) -> None:
    _import_taxonomy(client)

    response = client.post(
        "/api/questions/generate",
        json={
            "topic_id": 1,
            "subtopic_id": 1,
            "question_type": "debugging",
            "difficulty": "medium",
        },
    )

    assert response.status_code == 422
    assert "section" in response.json()["error"]["message"].lower()


def test_generation_rejects_an_unknown_question_type(client: TestClient) -> None:
    response = client.post(
        "/api/questions/generate",
        json={
            "topic_id": 1,
            "subtopic_id": 1,
            "question_type": "essay",
            "difficulty": "medium",
            "section_ids": [1],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_unknown_question_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/questions/4242")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# ----------------------------------------------------------------------- feedback


def test_review_endpoints_start_empty(client: TestClient) -> None:
    assert client.get("/api/reviews").json() == {"reviews": [], "total": 0}
    stats = client.get("/api/reviews/stats").json()
    assert stats == {
        "reviewed": 0,
        "approved": 0,
        "rejected": 0,
        "edited": 0,
        "reason_distribution": [],
    }


def test_reviewing_an_unknown_question_is_a_json_404(client: TestClient) -> None:
    response = client.post(
        "/api/questions/4242/review", json={"decision": ReviewDecision.APPROVE.value}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_review_rejects_an_unknown_decision(client: TestClient) -> None:
    response = client.post("/api/questions/1/review", json={"decision": "maybe"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


# -------------------------------------------------------------------- preferences


def test_preferences_start_empty(client: TestClient) -> None:
    assert client.get("/api/preferences").json() == {
        "preferences": [],
        "total": 0,
        "active_count": 0,
    }


def test_refresh_without_an_llm_reports_configuration_as_json(client: TestClient) -> None:
    # Test settings disable the LLM; refresh with no reviews short-circuits to 0.
    response = client.post("/api/preferences/refresh")

    assert response.status_code == 200
    assert response.json() == {"refreshed": 0, "preferences": []}


def test_correcting_an_unknown_preference_is_a_json_404(client: TestClient) -> None:
    response = client.post("/api/preferences/999/correct", json={"rule_text": "Be concise."})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_correcting_with_empty_text_is_refused_by_the_request_model(client: TestClient) -> None:
    response = client.post("/api/preferences/1/correct", json={"rule_text": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


# ------------------------------------------------------------------------- schema


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/config",
        "/api/counts",
        "/api/books",
        "/api/curriculum/versions",
        "/api/questions",
        "/api/reviews",
        "/api/reviews/stats",
        "/api/preferences",
    ],
)
def test_every_read_endpoint_answers_with_json(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


# ------------------------------------------------------------------------- schema


def test_openapi_documents_the_whole_api(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    for path in (
        "/api/health",
        "/api/config",
        "/api/counts",
        "/api/books",
        "/api/books/{book_id}",
        "/api/books/{book_id}/sections",
        "/api/books/{book_id}/sections/{section_id}",
        "/api/curriculum/versions",
        "/api/curriculum/approved",
        "/api/curriculum/versions/{version_id}",
        "/api/curriculum/subtopics/{subtopic_id}",
        "/api/questions",
        "/api/questions/generate",
        "/api/questions/{question_id}",
        "/api/questions/{question_id}/review",
        "/api/reviews",
        "/api/reviews/stats",
        "/api/preferences",
        "/api/preferences/refresh",
        "/api/preferences/{preference_id}/confirm",
        "/api/preferences/{preference_id}/correct",
        "/api/preferences/{preference_id}/remove",
    ):
        assert path in paths, f"{path} is missing from the OpenAPI schema"
