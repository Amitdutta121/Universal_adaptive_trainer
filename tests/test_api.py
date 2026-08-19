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

from app.config import Settings
from app.domain.enums import CurriculumStatus, JudgeMetricId, QuestionType, ReviewDecision
from app.generation.prompts import base_type_instruction
from app.persistence.repositories import (
    BookRepository,
    CurriculumRepository,
    TypeInstructionRepository,
)

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
        "learned_instructions": 0,
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


def test_an_older_approved_curriculum_can_be_made_active_again(client: TestClient) -> None:
    old = _import_taxonomy(client)["version"]["id"]
    _import_taxonomy(client)

    response = client.post(f"/api/curriculum/versions/{old}/activate")

    assert response.status_code == 200
    assert response.json()["version"]["id"] == old
    assert client.get("/api/curriculum/approved").json()["version"]["id"] == old


def test_single_generation_uses_the_active_curriculum_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.web.routes.api import questions as api_questions

    old = _import_taxonomy(client)["version"]["id"]
    _import_taxonomy(client)
    activate = client.post(f"/api/curriculum/versions/{old}/activate")
    assert activate.status_code == 200

    seen: dict[str, int] = {}

    class FakeGenerationService:
        def __init__(self, request_session) -> None:
            self._session = request_session

        def generate_for_sections(self, **kwargs: object) -> list[object]:
            seen["curriculum_version_id"] = int(kwargs["curriculum_version_id"])
            return []

    monkeypatch.setattr(api_questions, "GenerationService", FakeGenerationService)

    response = client.post(
        "/api/questions/generate",
        json={
            "question_type": "debugging",
            "difficulty": "medium",
            "section_ids": [1],
        },
    )

    assert response.status_code == 201, response.text
    assert seen["curriculum_version_id"] == old


def test_batch_generation_uses_the_active_curriculum_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.web.routes.api import questions as api_questions

    old = _import_taxonomy(client)["version"]["id"]
    _import_taxonomy(client)
    activate = client.post(f"/api/curriculum/versions/{old}/activate")
    assert activate.status_code == 200

    seen: dict[str, int] = {}

    class FakeGenerationService:
        def __init__(self, request_session) -> None:
            self._session = request_session

        def generate_batch(self, **kwargs: object) -> list[object]:
            seen["curriculum_version_id"] = int(kwargs["curriculum_version_id"])
            return []

    monkeypatch.setattr(api_questions, "GenerationService", FakeGenerationService)

    response = client.post(
        "/api/questions/generate-batch",
        json={
            "chunks": [
                {
                    "section_id": 1,
                    "easy": 1,
                    "question_types": ["debugging"],
                }
            ]
        },
    )

    assert response.status_code == 201, response.text
    assert seen["curriculum_version_id"] == old


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
        "curriculum_version_counts": {},
        "total": 0,
        "status": None,
        "curriculum_version_id": None,
    }


def test_question_list_filters_by_curriculum_version_across_the_whole_bank(
    client: TestClient, session: Session
) -> None:
    """The filter is applied before ``limit``, not to whatever page ``limit``
    already loaded -- otherwise an older match could fall off the page before
    the filter ever saw it.
    """
    from app.persistence.models import QuestionRow

    old_v1_question = QuestionRow(prompt="From version 1.", curriculum_version_id=1)
    session.add(old_v1_question)
    session.flush()
    for i in range(3):
        session.add(QuestionRow(prompt=f"From version 2, #{i}.", curriculum_version_id=2))
    session.commit()

    response = client.get("/api/questions", params={"curriculum_version_id": 1, "limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert [q["id"] for q in payload["questions"]] == [old_v1_question.id]
    assert payload["curriculum_version_id"] == 1
    assert payload["total"] == 4
    assert payload["curriculum_version_counts"] == {"1": 1, "2": 3}


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


def test_generation_plan_prices_a_selection_without_running_it(client: TestClient) -> None:
    book_id = _import_book(client)["id"]
    sections = client.get(f"/api/books/{book_id}/sections").json()["sections"]
    chosen = [sections[0]["id"], sections[1]["id"]]

    response = client.get(
        "/api/questions/generation-plan",
        params={"book_id": book_id, "section_ids": chosen},
    )

    assert response.status_code == 200
    plan = response.json()
    totals = plan["totals"]
    assert totals["sections_available"] == len(sections)
    assert totals["sections_selected"] == 2
    assert totals["questions_to_create"] == 2
    assert totals["generation_calls"] == 2
    # One judge call per advisory metric per question (ADR-031).
    assert totals["judge_calls"] == 2 * len(JudgeMetricId)
    assert totals["source_chars"] == sections[0]["char_count"] + sections[1]["char_count"]
    assert plan["blockers"] == []
    # Pricing a run must not create one.
    assert client.get("/api/questions").json()["total"] == 0


def test_generation_plan_groups_sections_by_chapter_and_marks_the_selection(
    client: TestClient,
) -> None:
    book_id = _import_book(client)["id"]
    section_id = client.get(f"/api/books/{book_id}/sections").json()["sections"][0]["id"]

    plan = client.get(
        "/api/questions/generation-plan",
        params={"book_id": book_id, "section_ids": [section_id]},
    ).json()

    assert [chapter["label"] for chapter in plan["chapters"]] == [
        "1 The Way of the Program",
        "2 Variables, Expressions and Statements",
    ]
    entries = {
        item["section"]["id"]: item for chapter in plan["chapters"] for item in chapter["sections"]
    }
    assert entries[section_id]["selected"] is True
    assert entries[section_id]["selectable"] is True
    assert entries[section_id]["existing_question_count"] == 0
    assert sum(1 for item in entries.values() if item["selected"]) == 1


def test_generation_plan_for_a_whole_book_selects_every_section(client: TestClient) -> None:
    book_id = _import_book(client)["id"]
    section_count = len(client.get(f"/api/books/{book_id}/sections").json()["sections"])

    plan = client.get(
        "/api/questions/generation-plan",
        params={"book_id": book_id, "all_sections": True},
    ).json()

    assert plan["totals"]["sections_selected"] == section_count
    assert plan["totals"]["judge_calls"] == section_count * len(JudgeMetricId)


def test_generation_plan_for_an_unknown_book_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/questions/generation-plan", params={"book_id": 4242})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --------------------------------------------------------------------- evaluation


def test_batch_run_list_is_empty_before_any_rerun(client: TestClient) -> None:
    assert client.get("/api/evaluation/batch-runs").json() == {"runs": [], "total": 0}


def test_submitting_a_rerun_without_configuration_is_json(client: TestClient) -> None:
    """Test settings leave the batch judge disabled, so this reports that."""
    response = client.post("/api/evaluation/batch-runs")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "configuration_error"


def test_unknown_batch_run_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/evaluation/batch-runs/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_polling_an_unknown_batch_run_is_a_json_404(client: TestClient) -> None:
    response = client.post("/api/evaluation/batch-runs/does-not-exist/poll")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_evaluation_history_of_an_unknown_question_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/questions/4242/evaluations")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_evaluation_history_is_newest_first_and_flags_the_current_one(
    client: TestClient, session: Session
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.domain.enums import EvaluationTrigger
    from app.evaluation import record_evaluation
    from app.evaluation.schema import PedagogicalEvalStatus, PedagogicalEvaluation
    from app.persistence.models import QuestionRow

    question = QuestionRow(prompt="What is printed?")
    session.add(question)
    session.flush()
    older = datetime.now(UTC) - timedelta(days=1)
    for created_at, model, trigger in (
        (older, "old/model", EvaluationTrigger.GENERATION),
        (datetime.now(UTC), "new/model", EvaluationTrigger.BATCH_RERUN),
    ):
        record_evaluation(
            session,
            question.id,
            PedagogicalEvaluation(
                question_id=question.id,
                status=PedagogicalEvalStatus.SKIPPED,
                overall_advisory_status="skipped",
                judge_model=model,
                created_at=created_at,
            ),
            run_id=f"run-{model}",
            trigger=trigger,
        )
    session.commit()

    payload = client.get(f"/api/questions/{question.id}/evaluations").json()

    assert payload["total"] == 2
    assert [entry["judge_model"] for entry in payload["evaluations"]] == [
        "new/model",
        "old/model",
    ]
    assert [entry["is_current"] for entry in payload["evaluations"]] == [True, False]
    assert payload["evaluations"][0]["trigger"] == "batch_rerun"


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


# ------------------------------------------------------------- type instructions


def test_every_type_is_listed_with_its_shipped_instruction(client: TestClient) -> None:
    """A type nobody has reviewed still has an instruction -- the shipped one."""
    payload = client.get("/api/instructions").json()

    entries = {entry["question_type"]: entry for entry in payload["instructions"]}
    assert set(entries) == {question_type.value for question_type in QuestionType}
    multiple_choice = entries["multiple_choice"]
    assert multiple_choice["learned"] is False
    assert multiple_choice["rules"] == []
    assert multiple_choice["available_reviews"] == 0
    assert multiple_choice["instruction"]


def test_refreshing_a_type_with_no_reviews_changes_nothing(client: TestClient) -> None:
    """Nothing to learn from is not an error, and must not invent rules."""
    response = client.post("/api/instructions/multiple_choice/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["learned"] is False
    assert payload["rule_count"] == 0
    assert payload["review_count"] == 0


def test_refreshing_an_unknown_type_is_a_json_422(client: TestClient) -> None:
    response = client.post("/api/instructions/not_a_type/refresh")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_deleting_a_learned_instruction_reverts_to_the_shipped_default(
    client: TestClient, session: Session
) -> None:
    TypeInstructionRepository(session).upsert(
        QuestionType.MULTIPLE_CHOICE,
        instruction="Use shorter distractors.",
        rules=[{"rule": "Keep options short.", "review_ids": [1]}],
        review_count=1,
    )
    session.commit()

    response = client.delete("/api/instructions/multiple_choice")

    assert response.status_code == 200
    payload = response.json()
    assert payload["question_type"] == QuestionType.MULTIPLE_CHOICE.value
    assert payload["learned"] is False
    assert payload["rules"] == []
    assert payload["review_count"] == 0
    assert payload["available_reviews"] == 0
    assert payload["instruction"] == base_type_instruction(QuestionType.MULTIPLE_CHOICE)
    assert TypeInstructionRepository(session).get(QuestionType.MULTIPLE_CHOICE) is None


def test_deleting_a_missing_instruction_is_a_json_404(client: TestClient) -> None:
    response = client.delete("/api/instructions/multiple_choice")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "not_found"
    assert "shipped instruction" in payload["error"]["message"]


def test_deleting_one_learned_rule_keeps_the_other_rules(
    client: TestClient, session: Session
) -> None:
    TypeInstructionRepository(session).upsert(
        QuestionType.MULTIPLE_CHOICE,
        instruction="ignored here",
        rules=[
            {"rule": "Keep options short.", "review_ids": [1]},
            {"rule": "Make exactly one option correct.", "review_ids": [2]},
        ],
        review_count=2,
    )
    session.commit()

    response = client.delete("/api/instructions/multiple_choice/rules/0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["learned"] is True
    assert payload["review_count"] == 2
    assert payload["rules"] == ["Make exactly one option correct."]
    assert "Keep options short." not in payload["instruction"]
    assert "Make exactly one option correct." in payload["instruction"]


def test_deleting_the_last_learned_rule_reverts_to_the_shipped_default(
    client: TestClient, session: Session
) -> None:
    TypeInstructionRepository(session).upsert(
        QuestionType.MULTIPLE_CHOICE,
        instruction="ignored here",
        rules=[{"rule": "Keep options short.", "review_ids": [1]}],
        review_count=1,
    )
    session.commit()

    response = client.delete("/api/instructions/multiple_choice/rules/0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["learned"] is False
    assert payload["rules"] == []
    assert payload["review_count"] == 0
    assert payload["instruction"] == base_type_instruction(QuestionType.MULTIPLE_CHOICE)
    assert TypeInstructionRepository(session).get(QuestionType.MULTIPLE_CHOICE) is None


# ------------------------------------------------------------------------- schema


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/config",
        "/api/counts",
        "/api/books",
        "/api/books/document-guide",
        "/api/curriculum/versions",
        "/api/curriculum/document-guide",
        "/api/questions",
        "/api/reviews",
        "/api/reviews/stats",
        "/api/instructions",
        "/api/calibration/results",
        "/api/calibration/pairs",
        "/api/evaluation/batch-runs",
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
        "/api/curriculum/document-guide",
        "/api/curriculum/versions/{version_id}",
        "/api/curriculum/versions/{version_id}/activate",
        "/api/curriculum/topics/{topic_id}",
        "/api/curriculum/subtopics/{subtopic_id}",
        "/api/questions",
        "/api/questions/generate",
        "/api/questions/{question_id}",
        "/api/questions/{question_id}/review",
        "/api/reviews",
        "/api/reviews/stats",
        "/api/instructions",
        "/api/instructions/{question_type}",
        "/api/instructions/{question_type}/rules/{rule_index}",
        "/api/instructions/{question_type}/refresh",
        "/api/calibration/results",
        "/api/calibration/pairs",
        "/api/evaluation/batch-runs",
        "/api/evaluation/batch-runs/{run_id}",
        "/api/evaluation/batch-runs/{run_id}/poll",
        "/api/questions/{question_id}/evaluations",
    ):
        assert path in paths, f"{path} is missing from the OpenAPI schema"


# ------------------------------------------------------------------------- cors


ALLOWED_ORIGIN = "http://localhost:5173"


def test_preflight_from_an_allowed_origin_is_accepted(client: TestClient) -> None:
    response = client.options(
        "/api/questions/generate",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_a_get_from_an_allowed_origin_carries_the_cors_header(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_an_error_response_still_carries_the_cors_header(client: TestClient) -> None:
    """Without this the browser reports a CORS failure instead of the 404."""
    response = client.get("/api/questions/999", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_an_unlisted_origin_gets_no_cors_header(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_middleware_is_absent_when_no_origins_are_configured(settings: Settings) -> None:
    from app.main import create_app

    app = create_app(settings.model_copy(update={"cors_allow_origins": []}))
    with TestClient(app) as bare_client:
        response = bare_client.get("/api/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
