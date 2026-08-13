"""Personalized context generator and prompt assembly."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import (
    Difficulty,
    PreferenceCategory,
    QuestionType,
    ReviewDecision,
)
from app.domain.preferences import confidence_from_evidence
from app.feedback import submit_review
from app.generation.schemas import DebuggingDraft
from app.generation.spec import build_question_spec
from app.ingestion import BookImportService
from app.persistence.models import PreferenceStatementRow, QuestionRow
from app.persistence.repositories import PreferenceRepository, QuestionRepository
from app.personalization.embeddings import FakeEmbedder
from app.personalization.generator import PersonalizedContextGenerator


class FakeClient:
    """Deterministic structured client for personalized generation tests."""

    def __init__(self, draft: BaseModel) -> None:
        self.draft = draft
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append({"system": system, "prompt": prompt, "model": response_model})
        return self.draft


def _debugging_draft(topic_id: int = 1, subtopic_ids: list[int] | None = None) -> DebuggingDraft:
    return DebuggingDraft(
        topic_id=topic_id,
        subtopic_ids=subtopic_ids or [1],
        prompt="Find the bug.",
        code="s = 'ab'\ns[0] = 'c'",
        reference_solution="Strings are immutable; build a new string.",
        tests=[{"assert": "assert True"}],
        explanation="Item assignment on str fails.",
    )


def _seed(session: Session, settings) -> tuple[object, object, object, list[int]]:
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
        version,
        version.topics[0],
        version.topics[0].subtopics[0],
        [section.id for chapter in book.chapters for section in chapter.sections],
    )


def _question(session: Session, **overrides: object) -> QuestionRow:
    values = {
        "prompt": "Write a loop.",
        "original_prompt": "Write a loop.",
        "reference_solution": "pass",
        "original_reference_solution": "pass",
        "tests": "assert True",
        "original_tests": "assert True",
        "generator_name": "base",
        "generator_version": "1",
    }
    values.update(overrides)
    row = QuestionRepository(session).add(QuestionRow(**values))
    session.commit()
    assert row.id is not None
    return row


def _seed_with_feedback(session: Session, settings) -> tuple[object, object, object, list[int]]:
    version, topic, subtopic, section_ids = _seed(session, settings)
    q = _question(
        session,
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[subtopic.id],
        spec={"source_section_ids": [section_ids[0]]},
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        prompt="Immutability debugging prompt about strings.",
    )
    submit_review(
        session,
        question_id=q.id,
        decision=ReviewDecision.APPROVE,
        comment="Good immutability example.",
    )
    PreferenceRepository(session).add(
        PreferenceStatementRow(
            rule_text="Prefer concise prompts.",
            category=PreferenceCategory.WORDING,
            evidence_count=2,
            confidence=confidence_from_evidence(2),
            supporting_review_ids=([1]),
        )
    )
    session.commit()
    return version, topic, subtopic, section_ids


def test_personalized_descriptor(session: Session, settings) -> None:
    gen = PersonalizedContextGenerator(
        session=session,
        client=FakeClient(_debugging_draft()),
        embedder=FakeEmbedder(dim=8),
    )
    assert gen.descriptor.label() == "personalized:personalized-context@1"


def test_prompt_includes_examples_and_style_disclaimer(session: Session, settings) -> None:
    version, topic, subtopic, section_ids = _seed_with_feedback(session, settings)
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = FakeClient(_debugging_draft(topic.id, [subtopic.id]))
    gen = PersonalizedContextGenerator(session=session, client=client, embedder=FakeEmbedder(dim=8))

    gen.generate_one(spec, version=version)

    system, user = client.calls[0]["system"], client.calls[0]["prompt"]
    combined = f"{system}\n{user}".lower()
    assert "style and pedagogy only" in combined
    assert "Professor preferences" in user or "Approved" in user


def test_no_feedback_still_personalized_descriptor(session: Session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = FakeClient(_debugging_draft(topic.id, [subtopic.id]))
    gen = PersonalizedContextGenerator(session=session, client=client, embedder=FakeEmbedder(dim=8))

    question = gen.generate_one(spec, version=version)

    assert question.generator_name == "personalized-context"
    assert question.personalization_context is not None
    payload = question.personalization_context
    assert payload["retrieved_review_ids"] == []


def test_base_generator_unchanged() -> None:
    from app.generation.base import DESCRIPTOR

    assert DESCRIPTOR.name == "base" and DESCRIPTOR.version == "1"
