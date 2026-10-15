"""The JSON API, over real HTTP.

Covers the shape of every endpoint that mirrors an existing professor
capability, plus the two invariants that matter to a client: errors always come
back as JSON under ``/api``, and an invalid upload changes nothing.
"""

from __future__ import annotations

import book_documents as docs
import pymupdf
import pytest
from book_uploads import upload_book
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import (
    CurriculumStatus,
    GuidelineStatus,
    QuestionStatus,
    QuestionType,
    ReviewDecision,
)
from app.generation.prompts import base_type_instruction
from app.persistence.models import MemoryGuidelineRow
from app.persistence.repositories import (
    BookRepository,
    CurriculumRepository,
)
from app.question_types import implemented_types
from app.subjects import PYTHON_PROFILE

VALID_TAXONOMY = (
    b'{"schema_version":"1","label":"Uploaded","topics":['
    b'{"name":"Loops","subtopics":[{"name":"While loops"},{"name":"For loops"}]}]}'
)


def _import_chunked_book(client: TestClient) -> tuple[dict, list[dict]]:
    """Think Python uploaded as a PDF, and its chunks: one per section, in reading order."""
    book = upload_book(
        client,
        files={"file": ("think_python.pdf", docs.to_pdf(docs.think_python()), "application/pdf")},
    )
    chunks = client.get("/api/chunks", params={"book_id": book["id"]}).json()["chunks"]
    return book, chunks


def _one_page_pdf(text: str = "Chapter 1\n\nHello.") -> bytes:
    """A tiny, real PDF, for exercising the PDF import and source-file routes."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _import_pdf_book(client: TestClient) -> dict:
    return upload_book(client, files={"file": ("textbook.pdf", _one_page_pdf(), "application/pdf")})


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

    assert payload["supported_book_extensions"] == [".docx", ".pdf", ".pptx"]
    assert "book_schema_version" not in payload
    assert [option["value"] for option in payload["difficulties"]] == ["easy", "medium", "hard"]
    assert {option["value"] for option in payload["question_types"]} == {
        "multiple_choice",
        "true_false",
        "output_prediction",
        "code_completion",
        "debugging",
        "parsons",
        "coding",
        "numeric_response",
        "equation_response",
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
    book, _ = _import_chunked_book(client)

    assert book["title"] == "Think Python"
    assert book["author"] == "Allen B. Downey"
    assert book["status"] == "imported"
    assert book["source_format"] == "book_pdf"
    assert BookRepository(session).count() == 1


def test_book_detail_reports_the_current_chunk_version(client: TestClient) -> None:
    book, chunks = _import_chunked_book(client)

    payload = client.get(f"/api/books/{book['id']}").json()

    assert payload["book"]["id"] == book["id"]
    assert (payload["chunk_count"], payload["current_version"]) == (4, 1)
    assert len(chunks) == 4
    assert "chapters" not in payload  # the chapter/section tree is retired


def test_book_source_streams_the_retained_pdf(client: TestClient) -> None:
    book_id = _import_pdf_book(client)["id"]

    response = client.get(f"/api/books/{book_id}/source")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_book_source_for_a_book_with_no_retained_pdf_is_a_404(
    client: TestClient, session: Session
) -> None:
    book_id = docs.chunked_book(session, docs.think_python()).id
    session.commit()

    response = client.get(f"/api/books/{book_id}/source")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_book_source_for_an_unknown_book_is_a_404(client: TestClient) -> None:
    response = client.get("/api/books/999999/source")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_book_json_upload_is_refused_and_stores_nothing(
    client: TestClient, session: Session
) -> None:
    """The book JSON document format is retired: a book is uploaded as the file itself."""
    response = client.post(
        "/api/books",
        files={"file": ("book.json", docs.to_bytes(docs.think_python()), "application/json")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file"
    assert BookRepository(session).count() == 0


def test_unsupported_book_extension_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/books", files={"file": ("book.docx", b"whatever", "application/octet-stream")}
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file"


def test_an_unreadable_pdf_upload_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/books", files={"file": ("book.pdf", b"%PDF-1.4\nnot a real pdf", "application/pdf")}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_book_document"


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
        "topic_id": None,
        "run_id": None,
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


def test_question_list_filters_by_any_of_several_statuses(
    client: TestClient, session: Session
) -> None:
    """``status`` repeats: the listing keeps a question in any of the named statuses."""
    from app.persistence.models import QuestionRow

    approved = QuestionRow(prompt="Approved.", status=QuestionStatus.APPROVED)
    rejected = QuestionRow(prompt="Rejected.", status=QuestionStatus.REJECTED)
    session.add_all([approved, rejected, QuestionRow(prompt="Generated.")])
    session.commit()

    response = client.get("/api/questions", params={"status": ["approved", "rejected"]})

    assert response.status_code == 200
    payload = response.json()
    assert sorted(q["id"] for q in payload["questions"]) == sorted([approved.id, rejected.id])
    assert sorted(payload["status"]) == ["approved", "rejected"]
    assert payload["total"] == 3


def test_question_list_filters_by_any_of_several_topics_across_the_whole_bank(
    client: TestClient, session: Session
) -> None:
    """``topic_id`` repeats and is applied before ``limit``, like the status filter."""
    from app.persistence.models import QuestionRow

    old_topic_1 = QuestionRow(prompt="Topic 1.", topic_id=1)
    topic_2 = QuestionRow(prompt="Topic 2.", topic_id=2)
    session.add_all([old_topic_1, topic_2])
    session.flush()
    for i in range(3):
        session.add(QuestionRow(prompt=f"Topic 3, #{i}.", topic_id=3))
    session.add(QuestionRow(prompt="No topic."))
    session.commit()

    response = client.get("/api/questions", params={"topic_id": [1, 2], "limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert sorted(q["id"] for q in payload["questions"]) == sorted([old_topic_1.id, topic_2.id])
    assert sorted(payload["topic_id"]) == [1, 2]
    assert payload["total"] == 6


def test_question_list_filters_by_chunk_across_the_whole_bank(
    client: TestClient, session: Session
) -> None:
    """``chunk_id`` narrows to questions grounded in that one chunk.

    Grounding is read from the frozen spec (ADR-044), not a foreign key, so this
    exercises the same scan :meth:`count_grounded_in_chunks` already relies on.
    """
    from app.persistence.models import QuestionRow

    wanted = QuestionRow(
        prompt="From chunk 7.",
        spec={"source_chunk_ids": ["7" * 32]},
    )
    session.add(wanted)
    session.add(QuestionRow(prompt="From chunk 9.", spec={"source_chunk_ids": ["9" * 32]}))
    session.add(QuestionRow(prompt="No spec at all."))
    session.commit()

    response = client.get("/api/questions", params={"chunk_id": "7" * 32})

    assert response.status_code == 200
    payload = response.json()
    assert [q["id"] for q in payload["questions"]] == [wanted.id]
    assert payload["total"] == 3


def test_unknown_question_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/questions/4242")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_the_chunk_outline_lists_a_books_chunks_with_what_they_produced(
    client: TestClient, session: Session
) -> None:
    from app.persistence.models import QuestionRow

    book, chunks = _import_chunked_book(client)
    session.add(
        QuestionRow(prompt="q", original_prompt="q", spec={"source_chunk_ids": [chunks[0]["id"]]})
    )
    session.commit()

    outline = client.get("/api/chunks/outline", params={"book_id": book["id"]}).json()

    assert outline["book"]["id"] == book["id"]
    assert [entry["chunk"]["id"] for entry in outline["chunks"]] == [c["id"] for c in chunks]
    counts = {e["chunk"]["id"]: e["existing_question_count"] for e in outline["chunks"]}
    assert counts[chunks[0]["id"]] == 1 and counts[chunks[1]["id"]] == 0
    assert outline["chunks"][0]["chunk"]["char_count"] == len(chunks[0]["text"])
    assert "text" not in outline["chunks"][0]["chunk"]


def test_the_chunk_outline_of_an_unknown_book_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/chunks/outline", params={"book_id": 4242})

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
    assert set(entries) == {question_type.value for question_type in implemented_types()}
    multiple_choice = entries["multiple_choice"]
    assert multiple_choice["learned"] is False
    assert multiple_choice["rules"] == []
    assert multiple_choice["available_reviews"] == 0
    assert multiple_choice["instruction"]


def test_an_active_guideline_reaches_the_listed_instruction(
    client: TestClient, session: Session
) -> None:
    """The list shows the text the generator receives: shipped + active guidelines only."""
    for text, status in (
        ("Keep options short.", GuidelineStatus.ACTIVE),
        ("Waiting for a second review.", GuidelineStatus.PENDING),
    ):
        session.add(
            MemoryGuidelineRow(
                target="generator:multiple_choice",
                subject=PYTHON_PROFILE.personal_key,
                text=text,
                review_ids=[1, 2] if status is GuidelineStatus.ACTIVE else [3],
                status=status,
                confirmed_by_professor=False,
            )
        )
    session.commit()

    listed = client.get("/api/instructions").json()["instructions"]
    entries = {entry["question_type"]: entry for entry in listed}

    multiple_choice = entries["multiple_choice"]
    assert multiple_choice["learned"] is True
    assert multiple_choice["rules"] == ["Keep options short."]
    assert multiple_choice["review_count"] == 2
    assert multiple_choice["instruction"].startswith(
        base_type_instruction(QuestionType.MULTIPLE_CHOICE)
    )
    assert "Waiting for a second review." not in multiple_choice["instruction"]
    assert entries["true_false"]["learned"] is False
    assert client.get("/api/counts").json()["learned_instructions"] == 1


def test_the_retired_rule_endpoints_are_gone(client: TestClient) -> None:
    """Guidelines are learned by the lesson run and edited under /api/guidelines (m5)."""
    assert client.post("/api/instructions/multiple_choice/refresh").status_code in {404, 405}
    assert client.delete("/api/instructions/multiple_choice").status_code in {404, 405}


# ------------------------------------------------------------------------- schema


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/config",
        "/api/counts",
        "/api/books",
        "/api/curriculum/versions",
        "/api/curriculum/document-guide",
        "/api/questions",
        "/api/reviews",
        "/api/reviews/stats",
        "/api/instructions",
        "/api/guidelines",
        "/api/judges/scorecard",
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
        "/api/chunks",
        "/api/chunks/{chunk_id}",
        "/api/chunks/outline",
        "/api/generation-runs",
        "/api/curriculum/versions",
        "/api/curriculum/approved",
        "/api/curriculum/document-guide",
        "/api/curriculum/versions/{version_id}",
        "/api/curriculum/versions/{version_id}/activate",
        "/api/curriculum/topics/{topic_id}",
        "/api/curriculum/subtopics/{subtopic_id}",
        "/api/questions",
        "/api/questions/{question_id}",
        "/api/questions/{question_id}/review",
        "/api/reviews",
        "/api/reviews/stats",
        "/api/instructions",
        "/api/guidelines",
        "/api/guidelines/{guideline_id}",
        "/api/guidelines/{guideline_id}/confirm",
        "/api/judges/scorecard",
        "/api/calibration/results",
        "/api/calibration/pairs",
        "/api/evaluation/batch-runs",
        "/api/evaluation/batch-runs/{run_id}",
        "/api/evaluation/batch-runs/{run_id}/poll",
        "/api/questions/{question_id}/evaluations",
    ):
        assert path in paths, f"{path} is missing from the OpenAPI schema"
    # Replaced by POST /api/generation-runs (ADR-066).
    for gone in (
        "/api/questions/generate",
        "/api/questions/{question_id}/regenerate",
        "/api/questions/generate-batch",
        "/api/questions/batch-plan",
        "/api/questions/generation-plan",
        "/api/coverage/generation-runs",
    ):
        assert gone not in paths, f"{gone} should be gone"
    assert "post" not in paths["/api/rounds/{round_id}"] and "/api/rounds" not in paths


# ------------------------------------------------------------------------- cors


ALLOWED_ORIGIN = "http://localhost:5173"


def test_preflight_from_an_allowed_origin_is_accepted(client: TestClient) -> None:
    response = client.options(
        "/api/generation-runs",
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
