"""HTTP surface: every section, the dashboard, health and error handling."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.web.navigation import NAV_SECTIONS

REQUIRED_LABELS = (
    "Books",
    "Curriculum",
    "Questions",
    "Professor Feedback",
    "Instructions",
    "Coverage",
    "Students",
)


def test_navigation_declares_exactly_the_required_sections() -> None:
    assert tuple(section.label for section in NAV_SECTIONS) == REQUIRED_LABELS


def test_dashboard_loads(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Adaptive Trainer" in response.text


def test_dashboard_links_to_every_section(client: TestClient) -> None:
    body = client.get("/").text
    for section in NAV_SECTIONS:
        assert f'href="{section.path}"' in body, f"missing link to {section.path}"
        assert section.label in body


@pytest.mark.parametrize("section", NAV_SECTIONS, ids=lambda s: s.key)
def test_each_section_page_loads_with_full_navigation(client: TestClient, section: object) -> None:
    response = client.get(section.path)  # type: ignore[attr-defined]
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # The heading is present...
    assert section.label in response.text  # type: ignore[attr-defined]
    # ...and every other section stays reachable from it.
    for other in NAV_SECTIONS:
        assert f'href="{other.path}"' in response.text


def test_section_pages_report_honest_empty_state(client: TestClient) -> None:
    assert "No books have been imported yet." in client.get("/books").text
    assert "No curriculum version has been approved yet." in client.get("/curriculum").text
    assert "No questions have been generated yet." in client.get("/questions").text
    assert "No professor reviews have been recorded yet." in client.get("/feedback").text
    # Every type is listed even with nothing learned, so the honest empty state is
    # "shipped instruction", not an empty page.
    assert "Shipped instruction" in client.get("/instructions").text


def test_students_page_states_the_fixed_adaptive_mechanism(client: TestClient) -> None:
    body = client.get("/students").text
    assert "BKT" in body
    assert "roulette" in body.lower()
    assert "passed_tests / total_tests" in body


def test_stylesheet_is_served(client: TestClient) -> None:
    response = client.get("/static/css/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database_ok"] is True
    assert payload["environment"] == "test"
    # Test settings deliberately disable the LLM.
    assert payload["llm_configured"] is False


def test_request_id_header_is_returned(client: TestClient) -> None:
    assert client.get("/").headers.get("X-Request-ID")


def test_supplied_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_unknown_page_renders_the_html_error_page(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "Error 404" in response.text


def test_unknown_api_route_returns_json_error(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"


def test_openapi_schema_is_available(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
