"""Professor pages for preferences and personalized question generation."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import (
    PreferenceCategory,
    PreferenceConfirmationState,
    QuestionStatus,
    RejectionReason,
    ReviewDecision,
)
from app.errors import ConfigurationError
from app.feedback import submit_review
from app.generation.schemas import DebuggingDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.models import PreferenceStatementRow, QuestionRow
from app.persistence.repositories import PreferenceRepository, QuestionRepository
from app.personalization.embeddings import FakeEmbedder
from app.personalization.learner import PreferenceCandidate, PreferenceExtractionResult


class FakeClient:
    """Return one typed draft without making a network request."""

    def __init__(self, topic_id: int = 1, subtopic_ids: list[int] | None = None) -> None:
        self.topic_id = topic_id
        self.subtopic_ids = subtopic_ids or [1]

    @property
    def description(self) -> str:
        return "fake/test-model"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        del system, prompt
        if response_model is PreferenceExtractionResult:
            return PreferenceExtractionResult(
                preferences=[
                    PreferenceCandidate(
                        rule_text="Prefer concise prompts.",
                        category=PreferenceCategory.WORDING,
                        supporting_review_ids=[1],
                    )
                ]
            )
        if response_model is not DebuggingDraft:
            from llm_fakes import verdict_for

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


def _seed_generation_context(session: Session, settings: Any) -> tuple[int, int, int, int, int]:
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
        version.topics[0].id,
        version.topics[0].subtopics[0].id,
        book.chapters[0].sections[0].id,
        version.id,
    )


def _seed_reviews(session: Session) -> list[int]:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Write a loop.",
            original_prompt="Write a loop.",
            reference_solution="pass",
            original_reference_solution="pass",
            tests="assert True",
            original_tests="assert True",
            generator_name="base",
            generator_version="1",
            status=QuestionStatus.VALIDATION_PASSED,
        )
    )
    session.commit()
    assert row.id is not None
    review = submit_review(
        session,
        question_id=row.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.POOR_WORDING],
        comment="Too verbose.",
    )
    session.commit()
    assert review.id is not None
    return [review.id]


def test_preferences_page_ok(client) -> None:
    response = client.get("/preferences")
    assert response.status_code == 200
    assert "Preferences" in response.text
    assert "Refresh preferences" in response.text


def test_refresh_preferences_post(client, session, monkeypatch) -> None:
    _seed_reviews(session)

    import app.web.routes.api.preferences as api_preferences

    def fake_refresh(request_session, **kwargs):
        repo = PreferenceRepository(request_session)
        if not repo.list_all(active_only=True):
            repo.add(
                PreferenceStatementRow(
                    rule_text="Prefer concise prompts.",
                    category=PreferenceCategory.WORDING,
                    evidence_count=1,
                    confidence=0.4,
                    supporting_review_ids=([1]),
                )
            )
            request_session.commit()
        return len(repo.list_all(active_only=True))

    monkeypatch.setattr(api_preferences, "refresh_preferences", fake_refresh)

    response = client.post("/preferences/refresh", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/preferences")


def test_refresh_preferences_llm_unavailable_shows_error(client, session, monkeypatch) -> None:
    _seed_reviews(session)

    import app.web.routes.api.preferences as api_preferences

    def fake_refresh(request_session, **kwargs):
        del request_session, kwargs
        raise ConfigurationError(
            "No LLM API key is configured.",
            detail="Set OPENROUTER_API_KEY in the environment.",
        )

    monkeypatch.setattr(api_preferences, "refresh_preferences", fake_refresh)

    response = client.post("/preferences/refresh", follow_redirects=False)
    assert response.status_code == 500
    assert "panel-error" in response.text
    assert "No LLM API key is configured." in response.text
    assert "OPENROUTER_API_KEY" in response.text


def test_preferences_confirm_correct_remove(client, session) -> None:
    row = PreferenceRepository(session).add(
        PreferenceStatementRow(
            rule_text="Prefer application over recall.",
            category=PreferenceCategory.EMPHASIS,
            evidence_count=2,
            confidence=0.4,
            supporting_review_ids=([1, 2]),
            confirmation_state=PreferenceConfirmationState.INFERRED,
        )
    )
    session.commit()
    assert row.id is not None

    confirm = client.post(f"/preferences/{row.id}/confirm", follow_redirects=False)
    assert confirm.status_code == 303
    session.expire_all()
    assert (
        PreferenceRepository(session).get(row.id).confirmation_state
        == PreferenceConfirmationState.CONFIRMED
    )

    correct = client.post(
        f"/preferences/{row.id}/correct",
        data={"rule_text": "Prefer short realistic programs."},
        follow_redirects=False,
    )
    assert correct.status_code == 303
    session.expire_all()
    corrected = PreferenceRepository(session).get(row.id)
    assert corrected.rule_text == "Prefer short realistic programs."
    assert corrected.confirmation_state == PreferenceConfirmationState.CORRECTED

    remove = client.post(f"/preferences/{row.id}/remove", follow_redirects=False)
    assert remove.status_code == 303
    session.expire_all()
    assert PreferenceRepository(session).get(row.id).active is False


def test_preferences_correct_empty_rule_shows_error(client, session) -> None:
    row = PreferenceRepository(session).add(
        PreferenceStatementRow(
            rule_text="Prefer application over recall.",
            category=PreferenceCategory.EMPHASIS,
            evidence_count=2,
            confidence=0.4,
            supporting_review_ids=([1, 2]),
            confirmation_state=PreferenceConfirmationState.INFERRED,
        )
    )
    session.commit()
    assert row.id is not None

    response = client.post(
        f"/preferences/{row.id}/correct",
        data={"rule_text": "   "},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "Corrected preference text must not be empty." in response.text
    assert "panel-error" in response.text

    session.expire_all()
    assert PreferenceRepository(session).get(row.id).rule_text == "Prefer application over recall."


def test_questions_form_shows_generator_choice(client, session, settings) -> None:
    book_id, _, _, _, _ = _seed_generation_context(session, settings)
    response = client.get(f"/questions?book_id={book_id}")
    assert response.status_code == 200
    assert 'name="generator"' in response.text
    assert 'value="base"' in response.text
    assert 'value="personalized"' in response.text


def test_generate_form_accepts_personalized(client, session, settings, monkeypatch) -> None:
    book_id, topic_id, subtopic_id, section_id, _ = _seed_generation_context(session, settings)

    import app.web.routes.api.questions as api_questions

    def fake_generation_service(request_session, **kwargs):
        return GenerationService(
            request_session, client=FakeClient(topic_id, [subtopic_id]), **kwargs
        )

    monkeypatch.setattr(api_questions, "GenerationService", fake_generation_service)
    monkeypatch.setattr(api_questions, "get_embedder", lambda settings=None: FakeEmbedder(dim=8))

    response = client.post(
        "/questions/generate",
        data={
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": str(section_id),
            "generator": "personalized",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    question_id = int(response.headers["location"].split("/")[-1])
    question = QuestionRepository(session).get(question_id)
    assert question.generator_name == "personalized-context"


def test_question_detail_shows_personalization_evidence(client, session) -> None:
    context = {
        "preference_ids": [7],
        "retrieved_review_ids": [3, 5],
        "profile_version": "1",
        "generator": "personalized-context@1",
    }
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Personalized prompt.",
            original_prompt="Personalized prompt.",
            reference_solution="pass",
            original_reference_solution="pass",
            tests="",
            original_tests="",
            generator_name="personalized-context",
            generator_version="1",
            status=QuestionStatus.VALIDATION_PASSED,
            personalization_context=context,
        )
    )
    session.commit()
    assert row.id is not None

    html = client.get(f"/questions/{row.id}").text
    assert "Personalization evidence" in html
    assert "Preference 7" in html or ">7<" in html
    assert "Review 3" in html or ">3<" in html
    assert "Review 5" in html or ">5<" in html
