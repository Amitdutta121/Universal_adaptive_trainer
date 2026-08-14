"""Professor pages for generating and inspecting base questions."""

from __future__ import annotations

import re
from typing import Any

import book_documents as docs
from llm_fakes import verdict_for
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.errors import MalformedModelOutputError
from app.generation.schemas import DebuggingDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService, SourceRetrieval
from app.persistence.repositories import BookRepository, QuestionRepository


class FakeClient:
    """Return one typed draft without making a network request."""

    def __init__(self, topic_id: int = 1, subtopic_ids: list[int] | None = None) -> None:
        self.topic_id = topic_id
        self.subtopic_ids = subtopic_ids or [1]

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
        if response_model is not DebuggingDraft:
            return verdict_for(response_model, self.topic_id, self.subtopic_ids)
        return DebuggingDraft(
            topic_id=self.topic_id,
            subtopic_ids=self.subtopic_ids,
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
    # No topic or subtopic control: the generator classifies its own question,
    # so offering the professor a choice here would suggest otherwise.
    assert 'name="subtopic_id"' not in response.text
    assert 'name="topic_id"' not in response.text
    assert f'value="{section_id}"' in response.text


def test_generate_post_creates_question(client, session, settings, monkeypatch) -> None:
    book_id, _, topic_id, subtopic_id, section_id = _seed(session, settings)

    import app.web.routes.api.questions as api_questions

    monkeypatch.setattr(
        api_questions,
        "GenerationService",
        lambda request_session: GenerationService(
            request_session, client=FakeClient(topic_id, [subtopic_id])
        ),
    )

    response = client.post(
        "/questions/generate",
        data={
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

    import app.web.routes.api.questions as api_questions

    monkeypatch.setattr(
        api_questions,
        "GenerationService",
        lambda request_session: GenerationService(
            request_session, client=FakeClient(topic_id, [subtopic_id])
        ),
    )

    response = client.post(
        "/questions/generate",
        data={
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

    import app.web.routes.api.questions as api_questions

    monkeypatch.setattr(
        api_questions,
        "GenerationService",
        lambda request_session: GenerationService(
            request_session, client=FakeClient(topic_id, [subtopic_id])
        ),
    )
    # A whole-book run always confirms first, so the page carries the selection
    # back with ``confirmed`` set rather than generating on the first POST.
    response = client.post(
        "/questions/generate",
        data={
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "all_sections": "true",
            "confirmed": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/questions?created={section_count}&ids=")
    assert QuestionRepository(session).count() == section_count


def test_generate_post_renders_malformed_model_output_in_form(
    client, session, settings, monkeypatch
) -> None:
    book_id, _, _topic_id, _subtopic_id, section_id = _seed(session, settings)

    class FailingGenerationService:
        def __init__(self, request_session: Session) -> None:
            self._session = request_session

        def generate_for_sections(self, **kwargs: object) -> list[object]:
            raise MalformedModelOutputError(
                "The model response was invalid.", detail="correct_option_index is out of range."
            )

    import app.web.routes.api.questions as api_questions

    monkeypatch.setattr(api_questions, "GenerationService", FailingGenerationService)
    response = client.post(
        "/questions/generate",
        data={
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

    import app.web.routes.api.questions as api_questions

    monkeypatch.setattr(
        api_questions,
        "GenerationService",
        lambda request_session: GenerationService(
            request_session, client=FakeClient(topic_id, [subtopic_id])
        ),
    )
    response = client.post(
        "/questions/generate",
        data={
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


def _wide_book(section_count: int) -> dict[str, Any]:
    """A one-chapter book with enough sections to cross the confirm threshold."""
    return {
        "schema_version": docs.SCHEMA_VERSION,
        "title": "Wide Book",
        "chapters": [
            {
                "number": "1",
                "title": "Everything",
                "structure_source": "structured_json",
                "sections": [
                    {
                        "number": f"1.{index}",
                        "title": f"Section {index}",
                        "text": f"Body text for section {index}.",
                        "structure_source": "structured_json",
                    }
                    for index in range(1, section_count + 1)
                ],
            }
        ],
    }


def test_chunk_plan_shows_chapters_text_and_costs(client, session, settings) -> None:
    book_id, _, _, _, section_id = _seed(session, settings)

    body = client.get(f"/questions?book_id={book_id}&section_ids={section_id}").text

    # Grouped by chapter, with the metadata the old <select> never showed.
    assert "1 The Way of the Program" in body
    assert "2 Variables, Expressions and Statements" in body
    assert "Pages 17\u201318" in body
    assert "chars" in body
    # The exact text the generator will receive, inline.
    assert "A program is a sequence of instructions." in body
    # And what the selected run costs, before it runs.
    assert "1 generation + 4 judge calls" in body


def test_chunk_plan_reports_questions_already_generated_per_section(
    client, session, settings, monkeypatch
) -> None:
    book_id, _, topic_id, subtopic_id, section_id = _seed(session, settings)

    import app.web.routes.api.questions as api_questions

    monkeypatch.setattr(
        api_questions,
        "GenerationService",
        lambda request_session: GenerationService(
            request_session, client=FakeClient(topic_id, [subtopic_id])
        ),
    )
    client.post(
        "/questions/generate",
        data={
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": str(section_id),
        },
        follow_redirects=False,
    )

    body = client.get(f"/questions?book_id={book_id}").text

    assert "1 question already" in body


def test_large_selection_confirms_before_generating_anything(client, session, settings) -> None:
    """A run over the threshold renders the plan and creates nothing."""
    BookImportService(session, settings).import_upload(
        filename="wide.json", data=docs.to_bytes(_wide_book(8))
    )
    TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
        ),
    )
    session.commit()
    book = BookRepository(session).list_usable()[0]
    section_ids = [section.id for section in SourceRetrieval(session).sections_in_book(book.id)]

    response = client.post(
        "/questions/generate",
        data={
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book.id),
            "section_ids": [str(section_id) for section_id in section_ids],
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Confirm generation" in response.text
    assert "Generate 8 questions" in response.text
    assert "8 generation + 32 judge" in " ".join(response.text.split())
    # Nothing was spent: the confirmation page is rendered instead of generating.
    assert QuestionRepository(session).count() == 0


def test_selection_at_or_below_threshold_generates_directly(
    client, session, settings, monkeypatch
) -> None:
    book_id, _, topic_id, subtopic_id, _ = _seed(session, settings)
    section_ids = [section.id for section in SourceRetrieval(session).sections_in_book(book_id)]

    import app.web.routes.api.questions as api_questions

    monkeypatch.setattr(
        api_questions,
        "GenerationService",
        lambda request_session: GenerationService(
            request_session, client=FakeClient(topic_id, [subtopic_id])
        ),
    )
    response = client.post(
        "/questions/generate",
        data={
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": [str(section_id) for section_id in section_ids],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert QuestionRepository(session).count() == len(section_ids)


def test_error_rerender_keeps_the_selection_and_the_settings(
    client, session, settings, monkeypatch
) -> None:
    book_id, _, _, _, section_id = _seed(session, settings)

    class FailingGenerationService:
        def __init__(self, request_session: Session) -> None:
            self._session = request_session

        def generate_for_sections(self, **kwargs: object) -> list[object]:
            raise MalformedModelOutputError("The model response was invalid.", detail="nope")

    import app.web.routes.api.questions as api_questions

    monkeypatch.setattr(api_questions, "GenerationService", FailingGenerationService)
    response = client.post(
        "/questions/generate",
        data={
            "difficulty": "hard",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": str(section_id),
        },
    )

    assert response.status_code == 502
    body = " ".join(response.text.split())
    # The chosen section is still ticked, and the settings are still chosen.
    assert re.search(rf'name="section_ids" value="{section_id}"[^>]*checked', body)
    assert 'value="hard" selected' in body
    assert 'value="debugging" selected' in body


def test_the_form_offers_no_generator_choice(client, session, settings) -> None:
    """One generator since ADR-033: personalization is the type instruction.

    There is nothing to choose between, so offering a choice would imply the
    professor could opt out of their own learned requirements.
    """
    book_id, _, _, _, _ = _seed(session, settings)

    body = " ".join(
        client.get(
            f"/questions?book_id={book_id}&difficulty=hard&question_type=debugging"
        ).text.split()
    )

    assert 'name="generator"' not in body
    assert "Personalized" not in body
    assert 'value="hard" selected' in body
    assert 'value="debugging" selected' in body
