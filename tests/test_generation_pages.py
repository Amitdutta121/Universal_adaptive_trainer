"""Professor pages for generating and inspecting base questions."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.errors import MalformedModelOutputError
from app.evaluation import DimensionEvaluation, JudgeDimensionId, JudgeModelResponse
from app.generation.schemas import DebuggingDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService, SourceRetrieval
from app.persistence.repositories import QuestionRepository


class FakeClient:
    """Return one typed draft without making a network request."""

    @property
    def description(self) -> str:
        """Provide stable generation provenance."""
        return "fake/test-model"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        """Return the debugging draft used by the page tests."""
        del system, prompt
        if response_model is JudgeModelResponse:
            return JudgeModelResponse(
                dimensions=[
                    DimensionEvaluation(
                        dimension=JudgeDimensionId.SUBTOPIC_ALIGNMENT,
                        score=5,
                        applicable=True,
                        confidence=1.0,
                        rationale="Aligned.",
                    )
                ]
            )
        return DebuggingDraft(
            prompt="Find the bug.",
            code="s = 'ab'\ns[0] = 'c'",
            reference_solution="Strings are immutable; build a new string.",
            tests=[{"assert": "assert True"}],
            explanation="Item assignment on str fails.",
        )


def _seed(session: Session, settings: Any) -> tuple[int, int, int, int, int]:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.think_python())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
        ),
    )
    session.commit()
    return (
        book.id,
        version.id,
        version.topics[0].id,
        version.topics[0].subtopics[0].id,
        book.chapters[0].sections[0].id,
    )


def test_questions_page_shows_generate_form_when_ready(client, session, settings) -> None:
    book_id, _, _, _, section_id = _seed(session, settings)

    response = client.get(f"/questions?book_id={book_id}")

    assert response.status_code == 200
    assert "Generate Question" in response.text
    assert "Immutability" in response.text
    assert f'value="{section_id}"' in response.text


def test_generate_post_creates_question(client, session, settings, monkeypatch) -> None:
    book_id, _, topic_id, subtopic_id, section_id = _seed(session, settings)

    import app.web.routes.pages as pages

    monkeypatch.setattr(
        pages,
        "GenerationService",
        lambda request_session: GenerationService(request_session, client=FakeClient()),
    )

    response = client.post(
        "/questions/generate",
        data={
            "topic_id": str(topic_id),
            "subtopic_id": str(subtopic_id),
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": str(section_id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/questions/")


def test_generate_post_multiple_sections_redirects_to_bank(
    client, session, settings, monkeypatch
) -> None:
    book_id, _, topic_id, subtopic_id, _ = _seed(session, settings)
    section_ids = [section.id for section in SourceRetrieval(session).sections_in_book(book_id)[:2]]

    import app.web.routes.pages as pages

    monkeypatch.setattr(
        pages,
        "GenerationService",
        lambda request_session: GenerationService(request_session, client=FakeClient()),
    )

    response = client.post(
        "/questions/generate",
        data={
            "topic_id": str(topic_id),
            "subtopic_id": str(subtopic_id),
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": [str(section_id) for section_id in section_ids],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/questions?created=2&ids=")
    assert not location.startswith("/questions/")

    body = client.get(location).text
    assert "Questions generated" in body
    assert "Created 2 questions" in body


def test_generate_post_all_sections_creates_one_question_per_book_section(
    client, session, settings, monkeypatch
) -> None:
    book_id, _, topic_id, subtopic_id, _ = _seed(session, settings)
    section_count = len(SourceRetrieval(session).sections_in_book(book_id))

    import app.web.routes.pages as pages

    monkeypatch.setattr(
        pages,
        "GenerationService",
        lambda request_session: GenerationService(request_session, client=FakeClient()),
    )
    response = client.post(
        "/questions/generate",
        data={
            "topic_id": str(topic_id),
            "subtopic_id": str(subtopic_id),
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "all_sections": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/questions?created={section_count}&ids=")
    assert QuestionRepository(session).count() == section_count


def test_generate_post_renders_malformed_model_output_in_form(
    client, session, settings, monkeypatch
) -> None:
    book_id, _, topic_id, subtopic_id, section_id = _seed(session, settings)

    class FailingGenerationService:
        def __init__(self, request_session: Session) -> None:
            self._session = request_session

        def generate_for_sections(self, **kwargs: object) -> list[object]:
            raise MalformedModelOutputError(
                "The model response was invalid.", detail="correct_option_index is out of range."
            )

    import app.web.routes.pages as pages

    monkeypatch.setattr(pages, "GenerationService", FailingGenerationService)
    response = client.post(
        "/questions/generate",
        data={
            "topic_id": str(topic_id),
            "subtopic_id": str(subtopic_id),
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": str(section_id),
        },
    )

    assert response.status_code == 502
    assert "The model response was invalid." in response.text
    assert "correct_option_index is out of range." in response.text


def test_detail_shows_prompt_and_source(client, session, settings, monkeypatch) -> None:
    book_id, _, topic_id, subtopic_id, section_id = _seed(session, settings)

    import app.web.routes.pages as pages

    monkeypatch.setattr(
        pages,
        "GenerationService",
        lambda request_session: GenerationService(request_session, client=FakeClient()),
    )
    response = client.post(
        "/questions/generate",
        data={
            "topic_id": str(topic_id),
            "subtopic_id": str(subtopic_id),
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": str(section_id),
        },
        follow_redirects=False,
    )

    body = client.get(response.headers["location"]).text

    assert "Find the bug." in body
    assert "Explanation" in body
    assert "Think Python" in body
    assert "Immutability" in body
