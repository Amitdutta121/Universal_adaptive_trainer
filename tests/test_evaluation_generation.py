"""GenerationService owns skip vs judge; judge cannot override deterministic fail."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionStatus, QuestionType
from app.errors import LLMRequestError
from app.evaluation.rubric import JudgeDimensionId
from app.evaluation.schema import (
    DimensionEvaluation,
    JudgeModelResponse,
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
)
from app.generation.schemas import OutputPredictionDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.repositories import QuestionRepository


def _dims() -> list[DimensionEvaluation]:
    return [
        DimensionEvaluation(
            dimension=dimension,
            score=5,
            applicable=True,
            confidence=0.9,
            rationale="great",
            issues=[],
        )
        for dimension in JudgeDimensionId
        if dimension is not JudgeDimensionId.DISTRACTOR_QUALITY
    ] + [
        DimensionEvaluation(
            dimension=JudgeDimensionId.DISTRACTOR_QUALITY,
            score=None,
            applicable=False,
            confidence=1.0,
            rationale="n/a",
            issues=[],
        )
    ]


class RecordingClient:
    """Generation draft + glowing judge response; counts judge calls."""

    def __init__(self) -> None:
        self.judge_calls = 0

    @property
    def description(self) -> str:
        return "fake/recording"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt
        if response_model is JudgeModelResponse:
            self.judge_calls += 1
            return JudgeModelResponse(dimensions=_dims())
        return OutputPredictionDraft(
            prompt="What is printed?",
            code="print(3)",
            expected_output="3",
            explanation="prints 3",
        )


class FailingDeterministicClient(RecordingClient):
    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt
        if response_model is JudgeModelResponse:
            self.judge_calls += 1
            return JudgeModelResponse(dimensions=_dims())
        return OutputPredictionDraft(
            prompt="What is printed?",
            code="print(4)",
            expected_output="3",
            explanation="wrong on purpose",
        )


class JudgeFailingClient(RecordingClient):
    """Generation draft succeeds while every judge request fails."""

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt
        if response_model is JudgeModelResponse:
            self.judge_calls += 1
            raise LLMRequestError("judge unavailable", detail="503")
        return OutputPredictionDraft(
            prompt="What is printed?",
            code="print(3)",
            expected_output="3",
            explanation="prints 3",
        )


def _seed(session: Session, settings: Any) -> tuple[Any, Any, Any, int]:
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


def test_pass_runs_judge_and_stores_completed(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = RecordingClient()
    row = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )[0]

    loaded = QuestionRepository(session).get(row.id)
    assert loaded.status is QuestionStatus.VALIDATION_PASSED
    evaluation = PedagogicalEvaluation.model_validate(loaded.pedagogical_eval)
    assert evaluation.status is PedagogicalEvalStatus.COMPLETED
    assert client.judge_calls == 1


def test_fail_skips_judge_and_stores_skipped(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = FailingDeterministicClient()
    row = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )[0]

    loaded = QuestionRepository(session).get(row.id)
    assert loaded.status is QuestionStatus.VALIDATION_FAILED
    evaluation = PedagogicalEvaluation.model_validate(loaded.pedagogical_eval)
    assert evaluation.status is PedagogicalEvalStatus.SKIPPED
    assert client.judge_calls == 0


def test_judge_error_preserves_validation_passed_question(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = JudgeFailingClient()
    row = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )[0]

    loaded = QuestionRepository(session).get(row.id)
    assert loaded.status is QuestionStatus.VALIDATION_PASSED
    evaluation = PedagogicalEvaluation.model_validate(loaded.pedagogical_eval)
    assert evaluation.status is PedagogicalEvalStatus.ERROR
    assert client.judge_calls == 3
