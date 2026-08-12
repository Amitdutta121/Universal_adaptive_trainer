"""LLM-backed advisory pedagogical evaluation with bounded retries."""

from __future__ import annotations

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


def build_judge_prompts(session: Session, question: Question) -> tuple[str, str]:
    """Return the ``(system, user)`` prompts for reviewing one question.

    Shared by the synchronous judge below and by the bulk re-run in
    :mod:`app.evaluation.batch_service` (ADR-030). The batch path builds its own
    request bodies, but it must not build its own rubric: two copies of these
    prompts would be free to drift, and a re-run would then answer a different
    question from the one the stored evaluation answered.

    Raises:
        AdaptiveTrainerError: if the question's sources or taxonomy cannot be
            resolved. Callers turn that into an ``error`` evaluation.
    """
    artifact, sources, taxonomy = _load_context(session, question)
    return (
        build_judge_system_prompt(),
        build_judge_user_prompt(
            question_artifact=artifact,
            source_sections=sources,
            taxonomy=taxonomy,
        ),
    )


class PedagogicalJudge:
    """Evaluate a generated question against its source and curriculum context."""

    def __init__(self, session: Session, *, client: StructuredLLMClient | None = None) -> None:
        self._session = session
        self._client = client or get_structured_client()

    def evaluate(self, question: Question) -> PedagogicalEvaluation:
        """Return completed evaluation or an advisory error after bounded retries."""
        try:
            system, prompt = build_judge_prompts(self._session, question)
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
    session: Session, question: Question
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    """Gather the question, its cited sections and its taxonomy names."""
    retrieval = SourceRetrieval(session)
    content = question.content or {}
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
        section = retrieval.get_section(section_id)
        sources.append(
            {
                "section_id": section_id,
                "citation": retrieval.section_source(section_id).citation(),
                "text": section.text,
            }
        )

    version = CurriculumRepository(session).get_with_tree(question.curriculum_version_id)
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


def _source_section_ids(question: Question) -> list[int]:
    """Collect unique source ids in frozen-request order, then content order."""
    section_ids: list[int] = []
    for payload, key in (
        (question.spec or {}, "source_section_ids"),
        (question.content or {}, "sources"),
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
