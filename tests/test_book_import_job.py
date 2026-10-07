"""Book import as a background job.

Extracting a textbook PDF can take minutes, so ``POST /api/books`` answers ``202 {job_id}``
once the quick checks pass and the Jobs panel follows the import. These tests pin what
the professor still sees in the dialog (a refusal the quick checks can make), what a
job reports when it succeeds or fails, and that a failed import leaves nothing behind.
"""

from __future__ import annotations

from pathlib import Path

import book_documents as docs
import pymupdf
from book_uploads import finished_job
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import JobKind, RoundStatus
from app.jobs.runner import create_job
from app.persistence.models import BackgroundJobRow
from app.persistence.repositories import BookRepository


def _pdf(*pages: str) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _stored_files(settings: Settings) -> list[Path]:
    directory = Path(settings.book_upload_dir)
    return list(directory.iterdir()) if directory.exists() else []


def test_a_pdf_import_is_a_job_that_ends_with_the_book(client: TestClient) -> None:
    response = client.post(
        "/api/books",
        files={"file": ("textbook.pdf", _pdf("Chapter 1\n\nHello."), "application/pdf")},
    )

    assert response.status_code == 202, response.text
    job = finished_job(client, response.json()["job_id"])
    book = job["result"]["book"]
    assert (job["kind"], job["status"], job["done"], job["total"]) == ("book_import", "done", 1, 1)
    assert job["title"] == "Import book · textbook.pdf"
    assert job["link"] == f"/books/{book['id']}"
    assert (job["can_cancel"], job["retry_label"]) == (False, None)
    listed = client.get("/api/books").json()["books"]
    assert [entry["id"] for entry in listed] == [book["id"]]


def test_a_json_import_keeps_the_professors_title(client: TestClient) -> None:
    response = client.post(
        "/api/books",
        data={"title": "My course reader"},
        files={"file": ("book.json", docs.to_bytes(docs.think_python()), "application/json")},
    )

    job = finished_job(client, response.json()["job_id"])
    assert job["result"]["book"]["title"] == "My course reader"


def test_quick_refusals_stay_in_the_dialog_and_queue_nothing(
    client: TestClient, session: Session, settings: Settings
) -> None:
    unreadable = client.post(
        "/api/books", files={"file": ("book.pdf", b"%PDF-1.4\nnot a real pdf", "application/pdf")}
    )
    invalid_json = client.post(
        "/api/books",
        files={"file": ("broken.json", b'{"schema_version":"1"}', "application/json")},
    )

    assert unreadable.status_code == 422
    assert invalid_json.status_code == 422
    assert unreadable.json()["error"]["code"] == "invalid_book_document"
    assert session.query(BackgroundJobRow).count() == 0
    assert _stored_files(settings) == []


def test_a_document_refused_inside_the_job_leaves_no_book_and_no_file(
    client: TestClient, session: Session, settings: Settings
) -> None:
    # Opens as a PDF (passes the quick check) but has no text to extract.
    response = client.post(
        "/api/books", files={"file": ("blank.pdf", _pdf("", ""), "application/pdf")}
    )

    assert response.status_code == 202, response.text
    job = finished_job(client, response.json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]
    assert (job["result"], job["link"], job["retry_label"]) == (None, None, None)
    assert BookRepository(session).count() == 0
    assert _stored_files(settings) == []


def test_a_running_import_cannot_be_cancelled(client: TestClient, session: Session) -> None:
    job = create_job(
        session,
        kind=JobKind.BOOK_IMPORT,
        title="Import book · x.pdf",
        total=1,
        request={},
        course_id=None,
    )
    job.status = RoundStatus.RUNNING
    session.commit()

    response = client.post(f"/api/jobs/job-{job.id}/cancel")

    assert response.status_code == 422, response.text
    assert "can't be stopped" in response.json()["error"]["message"]
    session.refresh(job)
    assert job.cancel_requested_at is None
