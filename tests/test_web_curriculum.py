"""The professor-facing curriculum flow, over real HTTP.

Covers the milestone as a user performs it: upload several books, press
Generate Curriculum, inspect the proposed hierarchy, then open a subtopic and see
what it was derived from. The LLM seam is overridden with the scripted client, so
the routes, templates and persistence are the real ones.
"""

from __future__ import annotations

import curriculum_fixtures as fixtures
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.routes.pages import structured_llm_client


@pytest.fixture
def scripted(configured_app: FastAPI) -> fixtures.ScriptedClient:
    """Install the scripted client behind the route's LLM dependency."""
    client = fixtures.ScriptedClient()
    configured_app.dependency_overrides[structured_llm_client] = lambda: client
    yield client
    configured_app.dependency_overrides.clear()


def upload_books(client: TestClient) -> None:
    for index, document in enumerate((fixtures.book_a(), fixtures.book_b(), fixtures.book_c())):
        response = client.post(
            "/books/upload",
            files={
                "file": (
                    f"book_{index}.json",
                    fixtures.to_bytes(document),
                    "application/json",
                )
            },
        )
        assert response.status_code == 200


def generate(client: TestClient) -> str:
    """Press Generate Curriculum and follow the redirect. Returns the page HTML."""
    response = client.post("/curriculum/generate", follow_redirects=False)
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert location.startswith("/curriculum/versions/")
    return client.get(location).text


class TestUnconfigured:
    def test_the_page_explains_what_is_missing(self, client: TestClient) -> None:
        """No credentials in the test environment, so the button must not appear."""
        page = client.get("/curriculum")
        assert page.status_code == 200
        assert "needs an LLM provider and API key" in page.text
        assert "Generate Curriculum</button>" not in page.text

    def test_generating_without_credentials_is_refused_inline(self, client: TestClient) -> None:
        response = client.post("/curriculum/generate")
        assert response.status_code == 400
        assert "needs an LLM provider and API key" in response.text
        assert "LLM_API_KEY" in response.text


class TestWithoutBooks:
    def test_the_page_points_at_the_books_page(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        page = client.get("/curriculum")
        assert "Upload at least one book document" in page.text

    def test_generating_without_books_is_refused_inline(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        response = client.post("/curriculum/generate")
        assert response.status_code == 422
        assert "no imported books" in response.text.lower()


class TestTheGenerationFlow:
    def test_the_button_appears_once_books_exist(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        upload_books(client)
        page = client.get("/curriculum").text
        assert "Generate Curriculum</button>" in page
        assert 'action="/curriculum/generate"' in page

    def test_generating_produces_a_browsable_hierarchy(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        upload_books(client)
        page = generate(client)

        assert "Strings" in page
        assert "Indexing" in page
        assert "Slicing" in page
        assert "Length" in page

    def test_the_hierarchy_shows_section_and_book_counts(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        upload_books(client)
        page = generate(client)
        assert "3 supporting sections" in page
        assert "3 books" in page
        assert "cross-book" in page

    def test_the_proposal_lists_the_books_it_came_from(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        upload_books(client)
        page = generate(client)
        assert "Think Python" in page
        assert "Python Crash Course" in page
        assert "Automate the Boring Stuff" in page

    def test_the_proposal_reports_how_it_was_produced(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        upload_books(client)
        page = generate(client)
        assert "scripted/test-model" in page
        assert "section-analysis/1" in page
        assert "cross-book-normalization/1" in page

    def test_the_latest_proposal_appears_on_the_index(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        upload_books(client)
        generate(client)
        page = client.get("/curriculum").text
        assert "Latest proposal" in page
        assert "Indexing" in page

    def test_nothing_is_shown_as_approved(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        upload_books(client)
        generate(client)
        assert "No curriculum version has been approved yet" in client.get("/curriculum").text


class TestSubtopicDetail:
    def open_indexing(self, client: TestClient) -> str:
        """Follow the hierarchy's link to the Indexing subtopic."""
        upload_books(client)
        page = generate(client)
        marker = '<a href="/curriculum/subtopics/'
        links = []
        for fragment in page.split(marker)[1:]:
            subtopic_id = fragment.split('"', 1)[0]
            links.append(f"/curriculum/subtopics/{subtopic_id}")
        assert links
        for link in links:
            detail = client.get(link)
            assert detail.status_code == 200
            if "<h1>Indexing</h1>" in detail.text:
                return detail.text
        raise AssertionError("No subtopic page for Indexing was linked from the hierarchy")

    def test_it_shows_the_definition_and_topic(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        page = self.open_indexing(client)
        assert "What a student can do with indexing." in page
        assert "Strings" in page

    def test_it_shows_the_merged_candidate_labels(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        page = self.open_indexing(client)
        assert "Accessing characters" in page
        assert "String indexing" in page
        assert "Selecting individual characters" in page

    def test_it_shows_why_they_were_grouped(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        page = self.open_indexing(client)
        assert "retrieving individual characters from strings using indices" in page

    def test_it_shows_representative_evidence(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        page = self.open_indexing(client)
        assert "letter = fruit[1]" in page
        assert "message[-1]" in page
        assert "spam[0]" in page

    def test_it_links_each_source_back_to_the_book_section(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        page = self.open_indexing(client)
        assert "/books/1/sections/" in page
        assert "Think Python, 8 Strings, 8.1 Accessing Characters" in page

    def test_it_shows_the_stable_id_and_review_status(
        self, client: TestClient, scripted: fixtures.ScriptedClient
    ) -> None:
        page = self.open_indexing(client)
        assert "sub-" in page
        assert "proposed" in page

    def test_an_unknown_subtopic_is_a_404(self, client: TestClient) -> None:
        assert client.get("/curriculum/subtopics/9999").status_code == 404


class TestFailuresStayOnThePage:
    def test_a_malformed_model_response_is_reported_inline(
        self, client: TestClient, configured_app: FastAPI
    ) -> None:
        broken = fixtures.ScriptedClient(stage_b_override={"groups": []})
        configured_app.dependency_overrides[structured_llm_client] = lambda: broken
        upload_books(client)

        response = client.post("/curriculum/generate")
        assert response.status_code == 502
        assert "Could not generate a curriculum" in response.text
        # Nothing was written, so the versions table is still empty.
        assert "No curriculum versions exist yet" in response.text

        configured_app.dependency_overrides.clear()

    def test_an_unknown_version_is_a_404(self, client: TestClient) -> None:
        assert client.get("/curriculum/versions/9999").status_code == 404
