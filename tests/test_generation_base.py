"""Base question generation through a mocked structured LLM client."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionKind, QuestionType
from app.generation.base import BaseQuestionGenerator
from app.generation.schemas import RESPONSE_MODEL_FOR, DebuggingDraft
from app.generation.service import GenerationService
from app.generation.spec import build_question_spec
from app.ingestion import BookImportService, SourceRetrieval
from app.persistence.repositories import QuestionRepository


class FakeClient:
    """Deterministic structured client used to exercise generator mapping."""

    def __init__(self, draft: BaseModel) -> None:
        self.draft = draft
        self.calls: list[dict[str, Any]] = []

    @property
    def description(self) -> str:
        """Return stable fake provenance."""
        return "fake/test-model"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        """Record the requested schema and return the configured typed draft."""
        self.calls.append({"system": system, "prompt": prompt, "model": response_model})
        return self.draft


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


def _debugging_draft() -> DebuggingDraft:
    return DebuggingDraft(
        prompt="Find the bug.",
        code="s = 'ab'\ns[0] = 'c'",
        reference_solution="Strings are immutable; build a new string.",
        tests=[{"call": "explain", "expected": "TypeError"}],
        explanation="Item assignment on str fails.",
    )


def test_base_generator_attaches_source_and_scoring_kind(session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[subtopic.id],
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = FakeClient(_debugging_draft())

    question = BaseQuestionGenerator(
        client=client, retrieval=SourceRetrieval(session)
    ).generate_one(spec, topic_name=topic.name, subtopic_names=[subtopic.name])

    assert question.kind is QuestionKind.TESTABLE_PROGRAM
    assert question.question_type is QuestionType.DEBUGGING
    assert question.generator_name == "base"
    assert question.generator_version == "1"
    assert question.content_json and f'"section_id": {section_ids[0]}' in question.content_json
    assert question.tests and "TypeError" in question.tests
    assert client.calls[0]["model"] is RESPONSE_MODEL_FOR[QuestionType.DEBUGGING]
    assert "Immutability" in client.calls[0]["prompt"]
    assert "section text" in client.calls[0]["prompt"].lower()


def test_base_generator_generates_one_unpersisted_question_per_section(
    session: Session, settings
) -> None:
    from app.generation import GenerationRequest

    version, topic, subtopic, section_ids = _seed(session, settings)
    client = FakeClient(_debugging_draft())

    questions = BaseQuestionGenerator(session=session, client=client).generate(
        GenerationRequest(
            curriculum_version_id=version.id,
            subtopic_id=subtopic.id,
            question_type=QuestionType.DEBUGGING,
            source_section_ids=section_ids[:2],
            difficulty=Difficulty.MEDIUM,
            count=1,
        )
    )

    assert len(questions) == 2
    assert [question.topic_id for question in questions] == [topic.id, topic.id]
    assert [question.subtopic_id for question in questions] == [subtopic.id, subtopic.id]
    assert all(question.id is None for question in questions)
    assert len(client.calls) == 2


def test_service_persists_one_question_per_selected_section(session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    client = FakeClient(_debugging_draft())
    service = GenerationService(session, client=client)

    rows = service.generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.EASY,
        source_section_ids=section_ids[:2],
    )

    assert len(rows) == 2
    assert QuestionRepository(session).count() == 2
    assert [row.topic_id for row in rows] == [topic.id, topic.id]
    assert all(row.question_type is QuestionType.DEBUGGING for row in rows)
    assert all(row.spec_json and '"source_section_ids":[' in row.spec_json for row in rows)
    assert len(client.calls) == 2
