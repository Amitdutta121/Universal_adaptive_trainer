"""The professor-facing Books workflow over HTTP."""

from __future__ import annotations

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from httpx import Response


def upload(client: TestClient, filename: str, data: bytes, title: str = "") -> Response:
    """Post a file to the upload endpoint without following the redirect."""
    return client.post(
        "/books/upload",
        files={"file": (filename, data, "application/json")},
        data={"title": title},
        follow_redirects=False,
    )


def upload_document(client: TestClient, document: dict, filename: str = "book.json") -> Response:
    return upload(client, filename, docs.to_bytes(document))


class TestBooksPage:
    def test_shows_the_upload_form(self, client: TestClient) -> None:
        body = client.get("/books").text
        assert 'action="/books/upload"' in body
        assert 'enctype="multipart/form-data"' in body
        assert 'name="file"' in body

    def test_the_file_input_accepts_only_json(self, client: TestClient) -> None:
        """The form must not invite a PDF; the page explains conversion separately."""
        body = client.get("/books").text
        assert 'accept=".json"' in body

    def test_documents_the_document_shape(self, client: TestClient) -> None:
        """A professor must be able to find out what a valid document looks like."""
        body = client.get("/books").text
        assert "schema_version" in body
        assert "structure_source" in body
        assert "docs/book_document_example.json" in body

    def test_empty_state(self, client: TestClient) -> None:
        assert "No books have been imported yet." in client.get("/books").text


class TestValidUpload:
    def test_redirects_to_the_new_book(self, client: TestClient) -> None:
        response = upload_document(client, docs.think_python())
        assert response.status_code == 303
        assert response.headers["location"].startswith("/books/")

    def test_the_book_then_appears_in_the_list(self, client: TestClient) -> None:
        upload_document(client, docs.think_python())
        body = client.get("/books").text
        assert "Think Python" in body
        assert "imported" in body

    def test_the_minimal_document_is_accepted(self, client: TestClient) -> None:
        assert upload_document(client, docs.minimal()).status_code == 303


class TestInvalidUpload:
    def test_a_pdf_is_rejected_with_an_explanation(self, client: TestClient) -> None:
        response = client.post(
            "/books/upload",
            files={"file": ("book.pdf", b"%PDF-1.4 ...", "application/pdf")},
            data={"title": ""},
        )
        assert response.status_code == 415
        assert "cannot be imported directly" in response.text
        assert "structured book JSON" in response.text
        # The form is still there to try again with.
        assert 'action="/books/upload"' in response.text

    def test_an_unsupported_type_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/books/upload",
            files={"file": ("notes.docx", b"nope", "application/octet-stream")},
            data={"title": ""},
        )
        assert response.status_code == 415
        assert "not a supported textbook format" in response.text

    def test_invalid_json_is_rejected_with_the_reason(self, client: TestClient) -> None:
        response = upload(client, "book.json", b'{"title": "Broken",}')
        assert response.status_code == 422
        assert "not valid JSON" in response.text

    def test_a_schema_violation_names_the_field(self, client: TestClient) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["text"] = ""
        response = upload_document(client, document)
        assert response.status_code == 422
        assert "does not match the expected structure" in response.text
        assert "text" in response.text

    def test_an_unknown_field_is_rejected(self, client: TestClient) -> None:
        document = docs.minimal()
        document["chapters"][0]["sections"][0]["txet"] = "typo"
        response = upload_document(client, document)
        assert response.status_code == 422
        assert "txet" in response.text

    def test_a_rejected_upload_creates_no_book(self, client: TestClient) -> None:
        upload(client, "book.json", b"{not json")
        assert "No books have been imported yet." in client.get("/books").text

    def test_missing_file_is_a_validation_error(self, client: TestClient) -> None:
        assert client.post("/books/upload", data={"title": "no file"}).status_code == 422


class TestBookDetailPage:
    @pytest.fixture
    def book_url(self, client: TestClient) -> str:
        return upload_document(client, docs.think_python()).headers["location"]

    def test_shows_the_expected_hierarchy(self, client: TestClient, book_url: str) -> None:
        """The professor-facing milestone: chapters with their sections beneath."""
        body = client.get(book_url).text
        assert "Think Python" in body
        for label in (
            "1 The Way of the Program",
            "1.1 What Is a Program?",
            "1.2 Running Python",
            "2 Variables, Expressions and Statements",
            "2.1 Values and Types",
            "2.2 Variables",
        ):
            assert label in body, f"missing {label!r}"

    def test_sections_link_to_their_own_page(self, client: TestClient, book_url: str) -> None:
        assert f'href="{book_url}/sections/' in client.get(book_url).text

    def test_shows_status_and_page_count(self, client: TestClient, book_url: str) -> None:
        body = client.get(book_url).text
        assert "imported" in body
        assert "292 pages" in body

    def test_shows_provenance(self, client: TestClient, book_url: str) -> None:
        body = client.get(book_url).text
        assert "think_python.pdf" in body
        assert "example-converter 1.0" in body
        assert "SHA-256" in body

    def test_unknown_book_is_a_404(self, client: TestClient) -> None:
        assert client.get("/books/999999").status_code == 404


class TestSectionPage:
    @pytest.fixture
    def section_url(self, client: TestClient) -> str:
        book_url = upload_document(client, docs.think_python()).headers["location"]
        body = client.get(book_url).text
        marker = f'href="{book_url}/sections/'
        start = body.index(marker) + len('href="')
        return body[start : body.index('"', start)]

    def test_shows_the_section_title_and_text(self, client: TestClient, section_url: str) -> None:
        body = client.get(section_url).text
        assert "1.1 What Is a Program?" in body
        assert "A program is a sequence of instructions." in body

    def test_shows_the_source_book_and_location(self, client: TestClient, section_url: str) -> None:
        body = client.get(section_url).text
        assert "Think Python" in body
        assert "Pages 17\u201318" in body

    def test_shows_a_citation(self, client: TestClient, section_url: str) -> None:
        assert (
            "Think Python, 1 The Way of the Program, 1.1 What Is a Program? (Pages 17\u201318)"
            in client.get(section_url).text
        )

    def test_shows_where_the_boundary_came_from(self, client: TestClient, section_url: str) -> None:
        body = client.get(section_url).text
        assert "high confidence" in body
        assert "table of contents" in body

    def test_unknown_section_is_a_404(self, client: TestClient) -> None:
        book_url = upload_document(client, docs.think_python()).headers["location"]
        assert client.get(f"{book_url}/sections/999999").status_code == 404

    def test_section_of_another_book_is_a_404(self, client: TestClient) -> None:
        """The URL asserts a book/section pair; a mismatch must not render."""
        first = upload_document(client, docs.think_python(), "a.json").headers["location"]
        second = upload_document(client, docs.minimal(), "b.json").headers["location"]
        body = client.get(second).text
        marker = f'href="{second}/sections/'
        start = body.index(marker) + len('href="')
        section_id = body[start : body.index('"', start)].rsplit("/", 1)[-1]
        assert client.get(f"{first}/sections/{section_id}").status_code == 404


class TestCaveatedUploads:
    def test_declared_caveats_are_shown_as_partial(self, client: TestClient) -> None:
        book_url = upload_document(client, docs.with_caveats()).headers["location"]
        body = client.get(book_url).text
        assert "partial" in body
        assert "Imported with caveats" in body
        assert "The source had no table of contents." in body

    def test_guessed_units_are_labelled_honestly(self, client: TestClient) -> None:
        book_url = upload_document(client, docs.with_caveats()).headers["location"]
        body = client.get(book_url).text
        assert "Untitled section (Pages 1\u20132)" in body
        assert "no heading found" in body
        assert "low confidence" in body
        assert "guessed by the producer" in body

    def test_informational_warnings_do_not_flag_the_book(self, client: TestClient) -> None:
        book_url = upload_document(client, docs.informational_only()).headers["location"]
        body = client.get(book_url).text
        assert "Imported with caveats" not in body
        # The warning is still shown, just not as a defect.
        assert "no page numbers" in body


class TestDashboardIntegration:
    def test_the_app_stays_healthy_after_an_import(self, client: TestClient) -> None:
        upload_document(client, docs.think_python())
        assert client.get("/").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"
