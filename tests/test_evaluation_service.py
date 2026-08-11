"""PedagogicalJudge retries and completed/error outcomes."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType
from app.domain.questions import Question
from app.errors import LLMRequestError, MalformedModelOutputError
from app.evaluation.rubric import JudgeDimensionId
from app.evaluation.schema import (
    DimensionEvaluation,
    JudgeModelResponse,
    PedagogicalEvalStatus,
)
from app.evaluation.service import JUDGE_MAX_ATTEMPTS, PedagogicalJudge
from app.ingestion import BookImportService


def _all_dims() -> list[DimensionEvaluation]:
    return [
        DimensionEvaluation(
            dimension=dim,
            score=4 if dim is not JudgeDimensionId.DISTRACTOR_QUALITY else None,
            applicable=dim is not JudgeDimensionId.DISTRACTOR_QUALITY,
            confidence=0.8,
            rationale="fine",
            issues=[],
        )
        for dim in JudgeDimensionId
    ]


class GoodJudgeClient:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def description(self) -> str:
        return "fake/judge-model"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        self.calls += 1
        assert response_model is JudgeModelResponse
        assert "print" in prompt.lower() or "prompt" in prompt.lower()
        return JudgeModelResponse(dimensions=_all_dims())


class FlakyJudgeClient:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.calls = 0

    @property
    def description(self) -> str:
        return "fake/flaky-judge"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt, response_model
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise MalformedModelOutputError("bad json", detail="nope")
        return JudgeModelResponse(dimensions=_all_dims())


class AlwaysBrokenJudgeClient:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def description(self) -> str:
        return "fake/broken-judge"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt, response_model
        self.calls += 1
        raise LLMRequestError("down", detail="503")


def _seed_question(session: Session, settings: Any) -> Question:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Output","subtopics":[{"name":"Printing","description":"print()"}]}]}'
        ),
    )
    session.commit()
    section = book.chapters[0].sections[0]
    return Question(
        id=1,
        curriculum_version_id=version.id,
        topic_id=version.topics[0].id,
        subtopic_id=version.topics[0].subtopics[0].id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        prompt="What is printed?",
        reference_solution="3",
        content_json=(
            '{"prompt":"What is printed?","code":"print(3)","expected_output":"3",'
            f'"sources":[{{"section_id":{section.id},"citation":"x"}}]}}'
        ),
        spec_json=(
            '{"curriculum_version_id":'
            + str(version.id)
            + ',"topic_id":'
            + str(version.topics[0].id)
            + ',"subtopic_ids":['
            + str(version.topics[0].subtopics[0].id)
            + '],"question_type":"output_prediction","difficulty":"easy",'
            + f'"source_section_ids":[{section.id}]}}'
        ),
    )


def test_judge_returns_completed(session: Session, settings: Any) -> None:
    client = GoodJudgeClient()
    question = _seed_question(session, settings)
    result = PedagogicalJudge(session, client=client).evaluate(question)
    assert result.status is PedagogicalEvalStatus.COMPLETED
    assert client.calls == 1
    assert result.judge_model == "fake/judge-model"
    assert result.overall_advisory_score is not None


def test_judge_retries_then_succeeds(session: Session, settings: Any) -> None:
    client = FlakyJudgeClient(failures_before_success=2)
    result = PedagogicalJudge(session, client=client).evaluate(_seed_question(session, settings))
    assert result.status is PedagogicalEvalStatus.COMPLETED
    assert client.calls == 3


def test_judge_returns_error_after_max_attempts(session: Session, settings: Any) -> None:
    client = AlwaysBrokenJudgeClient()
    result = PedagogicalJudge(session, client=client).evaluate(_seed_question(session, settings))
    assert result.status is PedagogicalEvalStatus.ERROR
    assert client.calls == JUDGE_MAX_ATTEMPTS
    assert result.error_detail
