"""GenerationService owns skip vs judge; judges cannot override deterministic fail."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from llm_fakes import verdict_for
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, JudgeGate, JudgeMetricId, QuestionStatus, QuestionType
from app.errors import LLMRequestError
from app.evaluation.schema import PedagogicalEvalStatus, PedagogicalEvaluation
from app.evaluation.service import JUDGE_MAX_ATTEMPTS
from app.generation.schemas import OutputPredictionDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.repositories import QuestionRepository


class RecordingClient:
    """Generation draft plus agreeing verdicts; counts judge calls."""

    code = "print(3)"

    def __init__(self, topic_id: int = 1, subtopic_ids: list[int] | None = None) -> None:
        self.topic_id = topic_id
        self.subtopic_ids = subtopic_ids or [1]
        self.judge_calls = 0

    @property
    def description(self) -> str:
        return "fake/recording"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt
        if response_model is not OutputPredictionDraft:
            self.judge_calls += 1
            return verdict_for(response_model, self.topic_id, self.subtopic_ids)
        return OutputPredictionDraft(
            topic_id=self.topic_id,
            subtopic_ids=self.subtopic_ids,
            prompt="What is printed?",
            code=self.code,
            expected_output="3",
            explanation="prints 3",
        )


class FailingDeterministicClient(RecordingClient):
    """Its code prints something other than the declared expected output."""

    code = "print(4)"


class JudgeFailingClient(RecordingClient):
    """Generation succeeds while every judge request fails."""

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        if response_model is not OutputPredictionDraft:
            self.judge_calls += 1
            raise LLMRequestError("judge unavailable", detail="503")
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model
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


def _generate(session: Session, version: Any, section_id: int, client: RecordingClient):
    return GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )[0]


def test_pass_runs_every_judge_and_stores_completed(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = RecordingClient(topic.id, [subtopic.id])

    row = _generate(session, version, section_id, client)

    loaded = QuestionRepository(session).get(row.id)
    assert loaded.status is QuestionStatus.VALIDATION_PASSED
    evaluation = PedagogicalEvaluation.model_validate(loaded.pedagogical_eval)
    assert evaluation.status is PedagogicalEvalStatus.COMPLETED
    assert evaluation.gate is JudgeGate.APPROVED
    assert client.judge_calls == len(JudgeMetricId)


def test_fail_skips_the_judges_and_stores_skipped(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = FailingDeterministicClient(topic.id, [subtopic.id])

    row = _generate(session, version, section_id, client)

    loaded = QuestionRepository(session).get(row.id)
    assert loaded.status is QuestionStatus.VALIDATION_FAILED
    evaluation = PedagogicalEvaluation.model_validate(loaded.pedagogical_eval)
    assert evaluation.status is PedagogicalEvalStatus.SKIPPED
    assert evaluation.gate is None
    assert client.judge_calls == 0


def test_judge_failure_preserves_the_question(session: Session, settings: Any) -> None:
    """The question still passes validation and still reaches review."""
    version, topic, subtopic, section_id = _seed(session, settings)
    client = JudgeFailingClient(topic.id, [subtopic.id])

    row = _generate(session, version, section_id, client)

    loaded = QuestionRepository(session).get(row.id)
    assert loaded.status is QuestionStatus.VALIDATION_PASSED
    evaluation = PedagogicalEvaluation.model_validate(loaded.pedagogical_eval)
    assert evaluation.status is PedagogicalEvalStatus.ERROR
    assert evaluation.gate is None
    assert client.judge_calls == JUDGE_MAX_ATTEMPTS * len(JudgeMetricId)


def test_generated_question_stores_its_claimed_subtopics(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = RecordingClient(topic.id, [subtopic.id])

    row = _generate(session, version, section_id, client)

    loaded = QuestionRepository(session).get(row.id)
    assert loaded.topic_id == topic.id
    assert list(loaded.subtopic_ids) == [subtopic.id]
