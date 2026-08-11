"""GenerationService selects base or personalized-context explicitly."""

from __future__ import annotations

import json
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
from app.domain.preferences import confidence_from_evidence, encode_review_ids
from app.evaluation import DimensionEvaluation, JudgeDimensionId, JudgeModelResponse
from app.feedback import submit_review
from app.generation.schemas import DebuggingDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.models import PreferenceStatementRow, QuestionRow
from app.persistence.repositories import PreferenceRepository, QuestionRepository
from app.personalization.embeddings import FakeEmbedder


class FakeClient:
    """Deterministic structured client for generation service tests."""

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
        return self.draft


def _debugging_draft() -> DebuggingDraft:
    return DebuggingDraft(
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


def _seed_with_feedback(session: Session, settings) -> tuple[object, object, object, list[int]]:
    version, topic, subtopic, section_ids = _seed(session, settings)
    row = QuestionRepository(session).add(
        QuestionRow(
            curriculum_version_id=version.id,
            topic_id=topic.id,
            subtopic_id=subtopic.id,
            question_type=QuestionType.DEBUGGING,
            difficulty=Difficulty.MEDIUM,
            prompt="Immutability debugging prompt about strings.",
            original_prompt="Immutability debugging prompt about strings.",
            reference_solution="pass",
            original_reference_solution="pass",
            tests="assert True",
            original_tests="assert True",
            generator_name="base",
            generator_version="1",
        )
    )
    session.commit()
    assert row.id is not None
    submit_review(
        session,
        question_id=row.id,
        decision=ReviewDecision.APPROVE,
        comment="Good immutability example.",
    )
    PreferenceRepository(session).add(
        PreferenceStatementRow(
            rule_text="Prefer concise prompts.",
            category=PreferenceCategory.WORDING,
            evidence_count=2,
            confidence=confidence_from_evidence(2),
            supporting_review_ids_json=encode_review_ids([1]),
        )
    )
    session.commit()
    return version, topic, subtopic, section_ids


def test_generation_service_selects_personalized(session: Session, settings) -> None:
    version, topic, subtopic, section_ids = _seed_with_feedback(session, settings)
    client = FakeClient(_debugging_draft())
    rows = GenerationService(
        session, client=client, embedder=FakeEmbedder(dim=8)
    ).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_ids[0]],
        generator="personalized",
    )

    assert rows[0].generator_name == "personalized-context"
    assert rows[0].personalization_context_json
    payload = json.loads(rows[0].personalization_context_json)
    assert "retrieved_review_ids" in payload


def test_generation_service_default_is_base(session: Session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    client = FakeClient(_debugging_draft())
    rows = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_ids[0]],
        generator="base",
    )

    assert rows[0].generator_name == "base"
    assert rows[0].personalization_context_json is None
