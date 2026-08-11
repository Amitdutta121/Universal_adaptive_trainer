"""Deterministic validation orchestration and generation integration."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionStatus, QuestionType
from app.domain.questions import Question
from app.evaluation import DimensionEvaluation, JudgeDimensionId, JudgeModelResponse
from app.generation.schemas import OutputPredictionDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.repositories import QuestionRepository
from app.validation import DeterministicQuestionValidator


class FakeClient:
    """Return one passing output-prediction draft."""

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
        return OutputPredictionDraft(
            prompt="What is printed?",
            code="print(3)",
            expected_output="3",
            explanation="The literal integer is printed.",
        )


class FailingFakeClient:
    """Return one output-prediction draft that fails deterministic validation."""

    @property
    def description(self) -> str:
        return "fake/failing-test-model"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        del system, prompt, response_model
        return OutputPredictionDraft(
            prompt="What is printed?",
            code="print(4)",
            expected_output="3",
            explanation="The literal integer is printed.",
        )


def _seed(session: Session, settings: Any) -> tuple[object, object, object, int]:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Output","subtopics":[{"name":"Printing"}]}]}'
        ),
    )
    session.commit()
    return (
        version,
        version.topics[0],
        version.topics[0].subtopics[0],
        book.chapters[0].sections[0].id,
    )


def test_validator_reports_unreadable_content_without_type_checks() -> None:
    report = DeterministicQuestionValidator().validate(
        Question(id=7, prompt="Anything", question_type=QuestionType.OUTPUT_PREDICTION)
    )

    assert report.question_id == 7
    assert report.passed is False
    assert report.checks[-1].name == "content_unreadable"
    assert "output_code_parses" not in {check.name for check in report.checks}


def test_generation_persists_passing_validation_report(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)

    rows = GenerationService(session, client=FakeClient()).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )

    loaded = QuestionRepository(session).get(rows[0].id)
    assert loaded.validation_report_json
    assert loaded.status is QuestionStatus.VALIDATION_PASSED


def test_generation_persists_failing_validation_report(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)

    rows = GenerationService(session, client=FailingFakeClient()).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )

    loaded = QuestionRepository(session).get(rows[0].id)
    assert loaded.validation_report_json
    assert loaded.status is QuestionStatus.VALIDATION_FAILED
