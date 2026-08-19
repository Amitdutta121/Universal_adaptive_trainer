"""Managing an imported book: renaming it, and deleting it.

The rule under test is what deletion costs. A question stores the sections it was
generated from inside its frozen spec rather than as a foreign key, so deleting a
book cannot cascade to the questions that cite it. Refusing by default, naming the
count, and proceeding only on an explicit override is the whole point of this
module -- a silent delete would leave citations pointing at nothing.
"""

from __future__ import annotations

from pathlib import Path

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import DomainRuleError, NotFoundError, ResourceInUseError
from app.ingestion import BookImportService, BookLibraryService
from app.persistence.models import BookRow, BookSectionRow, QuestionRow


def _import(session: Session, document: dict | None = None, filename: str = "book.json") -> BookRow:
    book = BookImportService(session).import_upload(
        filename=filename, data=docs.to_bytes(document or docs.think_python())
    )
    session.commit()
    return book


def _question_grounded_in(session: Session, section_id: int) -> QuestionRow:
    """A question whose frozen spec cites one section, as generation writes it."""
    question = QuestionRow(
        prompt="What does this print?", spec={"source_section_ids": [section_id]}
    )
    session.add(question)
    session.commit()
    return question


def _upload(client: TestClient, document: dict | None = None) -> dict:
    response = client.post(
        "/api/books",
        files={"file": ("book.json", docs.to_bytes(document or docs.think_python()))},
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestUpdateMetadata:
    def test_it_renames_a_book(self, session: Session) -> None:
        book = _import(session)
        updated = BookLibraryService(session).update_metadata(book.id, title="  Think Python 2e  ")
        assert updated.title == "Think Python 2e"

    def test_omitted_fields_are_left_alone(self, session: Session) -> None:
        book = _import(session)
        updated = BookLibraryService(session).update_metadata(book.id, notes="Used in CS 135.")
        assert updated.notes == "Used in CS 135."
        assert updated.title == "Think Python"
        assert updated.author == "Allen B. Downey"

    def test_an_empty_author_clears_it(self, session: Session) -> None:
        """An author the source never printed is a correction, not a mistake."""
        book = _import(session)
        assert BookLibraryService(session).update_metadata(book.id, author="  ").author is None

    def test_a_blank_title_is_refused(self, session: Session) -> None:
        """A book must stay identifiable in a list."""
        book = _import(session)
        with pytest.raises(DomainRuleError):
            BookLibraryService(session).update_metadata(book.id, title="   ")
        session.rollback()
        assert BookLibraryService(session).update_metadata(book.id, notes=None).title

    def test_an_unknown_book_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            BookLibraryService(session).update_metadata(999999, title="Nope")


class TestDelete:
    def test_it_removes_the_book_and_its_structure(self, session: Session) -> None:
        book = _import(session)
        book_id = book.id
        assert BookLibraryService(session).delete(book_id) == 0
        session.commit()
        with pytest.raises(NotFoundError):
            BookLibraryService(session).delete(book_id)
        assert session.get(BookRow, book_id) is None
        assert session.query(BookSectionRow).count() == 0

    def test_it_removes_the_retained_document(self, session: Session, settings: Settings) -> None:
        """The file exists to reproduce an import; the import is going with it."""
        book = _import(session)
        stored = Path(settings.book_upload_dir) / str(book.stored_filename)
        assert stored.is_file()
        BookLibraryService(session).delete(book.id)
        session.commit()
        assert not stored.exists()

    def test_a_missing_retained_document_does_not_block_deletion(
        self, session: Session, settings: Settings
    ) -> None:
        book = _import(session)
        (Path(settings.book_upload_dir) / str(book.stored_filename)).unlink()
        assert BookLibraryService(session).delete(book.id) == 0

    def test_an_unknown_book_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            BookLibraryService(session).delete(999999)


class TestDeleteWithQuestionsCitingTheBook:
    @pytest.fixture
    def book_with_question(self, session: Session) -> BookRow:
        book = _import(session)
        _question_grounded_in(session, book.sections[0].id)
        return book

    def test_the_citing_questions_are_counted(
        self, session: Session, book_with_question: BookRow
    ) -> None:
        assert BookLibraryService(session).grounded_question_count(book_with_question.id) == 1

    def test_a_question_from_another_book_is_not_counted(self, session: Session) -> None:
        first = _import(session, filename="a.json")
        second = _import(session, docs.minimal(), filename="b.json")
        _question_grounded_in(session, first.sections[0].id)
        assert BookLibraryService(session).grounded_question_count(second.id) == 0

    def test_deletion_is_refused_and_says_how_many(
        self, session: Session, book_with_question: BookRow
    ) -> None:
        with pytest.raises(ResourceInUseError) as exc:
            BookLibraryService(session).delete(book_with_question.id)
        assert "1 question" in str(exc.value)
        assert "force=true" in (exc.value.detail or "")

    def test_a_refusal_deletes_nothing(
        self, session: Session, settings: Settings, book_with_question: BookRow
    ) -> None:
        stored = Path(settings.book_upload_dir) / str(book_with_question.stored_filename)
        with pytest.raises(ResourceInUseError):
            BookLibraryService(session).delete(book_with_question.id)
        session.rollback()
        assert stored.is_file()
        assert BookLibraryService(session).grounded_question_count(book_with_question.id) == 1

    def test_force_deletes_and_reports_what_it_stranded(
        self, session: Session, book_with_question: BookRow
    ) -> None:
        assert BookLibraryService(session).delete(book_with_question.id, force=True) == 1
        session.commit()
        # The questions themselves are kept: their text is still worth reviewing.
        assert session.query(QuestionRow).count() == 1


class TestOverHttp:
    def test_patch_renames_a_book(self, client: TestClient) -> None:
        book = _upload(client)
        response = client.patch(f"/api/books/{book['id']}", json={"title": "Think Python 2e"})
        assert response.status_code == 200
        assert response.json()["title"] == "Think Python 2e"
        assert client.get("/api/books").json()["books"][0]["title"] == "Think Python 2e"

    def test_patch_refuses_a_blank_title(self, client: TestClient) -> None:
        book = _upload(client)
        response = client.patch(f"/api/books/{book['id']}", json={"title": " "})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "domain_rule_violation"

    def test_patch_refuses_an_unknown_field(self, client: TestClient) -> None:
        """Structure is declared by the document; it is not editable here."""
        book = _upload(client)
        response = client.patch(f"/api/books/{book['id']}", json={"page_count": 12})
        assert response.status_code == 422

    def test_patch_of_an_unknown_book_is_a_404(self, client: TestClient) -> None:
        assert client.patch("/api/books/999999", json={"title": "Nope"}).status_code == 404

    def test_delete_removes_the_book(self, client: TestClient) -> None:
        book = _upload(client)
        response = client.delete(f"/api/books/{book['id']}")
        assert response.status_code == 200
        assert response.json() == {"deleted_book_id": book["id"], "stranded_question_count": 0}
        assert client.get(f"/api/books/{book['id']}").status_code == 404
        assert client.get("/api/books").json()["total"] == 0

    def test_delete_of_an_unknown_book_is_a_404(self, client: TestClient) -> None:
        assert client.delete("/api/books/999999").status_code == 404

    def test_delete_is_refused_while_questions_cite_the_book(
        self, client: TestClient, session: Session
    ) -> None:
        book = _upload(client)
        section_id = client.get(f"/api/books/{book['id']}/sections").json()["sections"][0]["id"]
        _question_grounded_in(session, section_id)

        response = client.delete(f"/api/books/{book['id']}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "resource_in_use"
        assert client.get(f"/api/books/{book['id']}").status_code == 200

    def test_force_deletes_and_reports_the_stranded_count(
        self, client: TestClient, session: Session
    ) -> None:
        book = _upload(client)
        section_id = client.get(f"/api/books/{book['id']}/sections").json()["sections"][0]["id"]
        _question_grounded_in(session, section_id)

        response = client.delete(f"/api/books/{book['id']}", params={"force": True})
        assert response.status_code == 200
        assert response.json()["stranded_question_count"] == 1

    def test_the_detail_view_reports_what_deleting_would_strand(
        self, client: TestClient, session: Session
    ) -> None:
        book = _upload(client)
        section_id = client.get(f"/api/books/{book['id']}/sections").json()["sections"][0]["id"]
        assert client.get(f"/api/books/{book['id']}").json()["grounded_question_count"] == 0
        _question_grounded_in(session, section_id)
        assert client.get(f"/api/books/{book['id']}").json()["grounded_question_count"] == 1
