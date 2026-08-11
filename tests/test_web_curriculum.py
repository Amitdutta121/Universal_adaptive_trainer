"""The professor-facing fixed taxonomy upload flow, over real HTTP."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus
from app.persistence.repositories import CurriculumRepository

VALID_TAXONOMY = (
    b'{"schema_version":"1","label":"Uploaded","topics":['
    b'{"name":"Loops","subtopics":[{"name":"While loops"}]}]}'
)


def test_curriculum_page_offers_taxonomy_upload(client: TestClient) -> None:
    response = client.get("/curriculum")

    assert response.status_code == 200
    assert "Upload taxonomy" in response.text
    assert 'action="/curriculum/upload"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert "/curriculum/generate" not in response.text
    assert "schema_version" in response.text
    assert "docs/taxonomy_document_example.json" in response.text


def test_taxonomy_upload_creates_approved_version(client: TestClient, session: Session) -> None:
    response = client.post(
        "/curriculum/upload",
        files={"file": ("taxonomy.json", VALID_TAXONOMY, "application/json")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/curriculum/versions/")
    version = CurriculumRepository(session).get_latest()
    assert version is not None
    assert version.status == CurriculumStatus.APPROVED
    assert version.generated_by == "taxonomy-upload"

    version_page = client.get(response.headers["location"])
    assert version_page.status_code == 200
    assert "Uploaded fixed taxonomy" in version_page.text
    assert "Section analysis" not in version_page.text
    assert "Cross-book normalization" not in version_page.text


def test_invalid_taxonomy_json_stays_on_curriculum_page(client: TestClient) -> None:
    response = client.post(
        "/curriculum/upload",
        files={"file": ("taxonomy.json", b"{not json", "application/json")},
    )

    assert response.status_code == 400
    assert "Could not upload taxonomy" in response.text
    assert "not valid UTF-8 JSON" in response.text
    assert "No curriculum versions exist yet" in response.text


def test_an_unknown_version_is_a_404(client: TestClient) -> None:
    assert client.get("/curriculum/versions/9999").status_code == 404
