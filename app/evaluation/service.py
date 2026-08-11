"""LLM-backed advisory pedagogical evaluation with bounded retries."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.questions import Question
from app.errors import (
    AdaptiveTrainerError,
    LLMRequestError,
    MalformedModelOutputError,
    NotFoundError,
)
from app.evaluation.rubric import build_judge_system_prompt, build_judge_user_prompt
from app.evaluation.schema import (
    JudgeModelResponse,
    PedagogicalEvaluation,
    error_evaluation,
    evaluation_from_judge_response,
    humanize_judge_error_detail,
)
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.repositories import CurriculumRepository

JUDGE_MAX_ATTEMPTS = 3


class PedagogicalJudge:
    """Evaluate a generated question against its source and curriculum context."""

    def __init__(self, session: Session, *, client: StructuredLLMClient | None = None) -> None:
        self._session = session
        self._client = client or get_structured_client()
        self._retrieval = SourceRetrieval(session)
        self._curriculum = CurriculumRepository(session)

    def evaluate(self, question: Question) -> PedagogicalEvaluation:
        """Return completed evaluation or an advisory error after bounded retries."""
        try:
            artifact, sources, taxonomy = self._load_context(question)
            system = build_judge_system_prompt()
            prompt = build_judge_user_prompt(
                question_artifact=artifact,
                source_sections=sources,
                taxonomy=taxonomy,
            )
        except (AdaptiveTrainerError, LookupError, TypeError, ValueError) as exc:
            return error_evaluation(
                question_id=question.id,
                detail=_error_detail(exc),
                judge_model=self._client.description,
            )
        last_detail = "unknown"
        for _ in range(JUDGE_MAX_ATTEMPTS):
            try:
                response = self._client.complete_structured(
                    system=system,
                    prompt=prompt,
                    response_model=JudgeModelResponse,
                )
                return evaluation_from_judge_response(
                    response,
                    question_id=question.id,
                    judge_model=self._client.description,
                )
            except (LLMRequestError, MalformedModelOutputError) as exc:
                last_detail = humanize_judge_error_detail(str(exc.detail or exc))
        return error_evaluation(
            question_id=question.id,
            detail=last_detail,
            judge_model=self._client.description,
        )

    def _load_context(
        self, question: Question
    ) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
        content = _decode_object(question.content_json)
        artifact = {
            "prompt": question.prompt,
            "question_type": question.question_type.value if question.question_type else None,
            "difficulty": question.difficulty.value,
            "reference_solution": question.reference_solution,
            "tests": question.tests,
            "content": content,
        }
        sources = []
        for section_id in _source_section_ids(question):
            section = self._retrieval.get_section(section_id)
            sources.append(
                {
                    "section_id": section_id,
                    "citation": self._retrieval.section_source(section_id).citation(),
                    "text": section.text,
                }
            )

        version = self._curriculum.get_with_tree(question.curriculum_version_id)
        topic = next((topic for topic in version.topics if topic.id == question.topic_id), None)
        if topic is None:
            raise NotFoundError(
                "Question topic is not in its curriculum version.",
                detail=f"topic_id={question.topic_id}, curriculum_version_id={version.id}",
            )
        subtopic = next(
            (subtopic for subtopic in topic.subtopics if subtopic.id == question.subtopic_id),
            None,
        )
        if subtopic is None:
            raise NotFoundError(
                "Question subtopic is not in its topic.",
                detail=f"subtopic_id={question.subtopic_id}, topic_id={topic.id}",
            )
        taxonomy = {
            "topic_name": topic.name,
            "subtopic_name": subtopic.name,
            "subtopic_description": subtopic.description,
        }
        return artifact, sources, taxonomy


def _decode_object(raw_json: str | None) -> dict[str, Any]:
    """Decode persisted object JSON, treating malformed or non-object values as empty."""
    if raw_json is None:
        return {}
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _source_section_ids(question: Question) -> list[int]:
    """Collect unique source ids in frozen-request order, then content order."""
    section_ids: list[int] = []
    for payload, key in (
        (_decode_object(question.spec_json), "source_section_ids"),
        (_decode_object(question.content_json), "sources"),
    ):
        values = payload.get(key)
        if key == "sources" and isinstance(values, list):
            values = [source.get("section_id") for source in values if isinstance(source, dict)]
        if isinstance(values, list):
            for value in values:
                if type(value) is int and value not in section_ids:
                    section_ids.append(value)
    return section_ids


def _error_detail(exc: Exception) -> str:
    """Return a short professor-facing diagnostic for persisted advisory failures."""
    detail = getattr(exc, "detail", None) or str(exc) or type(exc).__name__
    return humanize_judge_error_detail(str(detail))
