"""Four advisory judges per question, each with its own bounded retries."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, JudgeMetricId
from app.domain.questions import Question
from app.errors import (
    AdaptiveTrainerError,
    LLMRequestError,
    MalformedModelOutputError,
    NotFoundError,
)
from app.evaluation.prompts import SYSTEM_PROMPT_FOR, JudgeContext, build_user_prompt
from app.evaluation.schema import (
    RESPONSE_MODEL_FOR,
    DifficultyVerdict,
    GeneratabilityVerdict,
    IssuesVerdict,
    MetricResult,
    PedagogicalEvaluation,
    SubtopicVerdict,
    evaluation_from_metrics,
    failed_metric,
    humanize_judge_error_detail,
    result_from_difficulty,
    result_from_generatability,
    result_from_issues,
    result_from_subtopic,
)
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.repositories import CurriculumRepository

JUDGE_MAX_ATTEMPTS = 3


def build_judge_context(session: Session, question: Question) -> JudgeContext:
    """Gather the question, its cited sections and the approved taxonomy.

    Shared by the synchronous judges below and by the bulk re-run in
    :mod:`app.evaluation.batch_service` (ADR-030). The batch path builds its own
    request bodies, but it must not build its own context: two copies would be
    free to drift, and a re-run would then answer a different question from the
    one the stored evaluation answered.

    Raises:
        AdaptiveTrainerError: if the question's sources or taxonomy cannot be
            resolved. Callers turn that into failed metrics.
    """
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
    taxonomy = [
        {
            "topic_id": topic.id,
            "topic_name": topic.name,
            "subtopics": [
                {
                    "subtopic_id": subtopic.id,
                    "name": subtopic.name,
                    "description": subtopic.description,
                }
                for subtopic in topic.subtopics
            ],
        }
        for topic in version.topics
    ]
    topic = next((row for row in version.topics if row.id == question.topic_id), None)
    if topic is None:
        raise NotFoundError(
            "Question topic is not in its curriculum version.",
            detail=f"topic_id={question.topic_id}, curriculum_version_id={version.id}",
        )
    by_id = {subtopic.id: subtopic for subtopic in topic.subtopics}
    missing = [sid for sid in question.subtopic_ids if sid not in by_id]
    if missing or not question.subtopic_ids:
        raise NotFoundError(
            "Question subtopics are not in its topic.",
            detail=f"subtopic_ids={question.subtopic_ids}, topic_id={topic.id}",
        )

    return JudgeContext(
        question_artifact=artifact,
        source_sections=sources,
        taxonomy=taxonomy,
        claimed_taxonomy={
            "topic_id": topic.id,
            "topic_name": topic.name,
            "subtopics": [
                {"subtopic_id": sid, "name": by_id[sid].name} for sid in question.subtopic_ids
            ],
        },
        requested_difficulty=question.difficulty.value,
        requested_question_type=(question.question_type.value if question.question_type else None),
    )


def result_from_verdict(metric: JudgeMetricId, verdict: object, question: Question) -> MetricResult:
    """Score one judge's answer against what the generator claimed.

    Lives beside the judges rather than inside the schema because scoring needs
    the question, and the schema deliberately knows nothing about one.
    """
    match verdict:
        case IssuesVerdict():
            return result_from_issues(verdict)
        case SubtopicVerdict():
            return result_from_subtopic(
                verdict,
                claimed=list(question.subtopic_ids),
                topic_id=question.topic_id or -1,
            )
        case DifficultyVerdict():
            return result_from_difficulty(verdict, requested=Difficulty(question.difficulty))
        case GeneratabilityVerdict():
            return result_from_generatability(verdict)
    msg = f"No scoring rule for {metric.value}"
    raise TypeError(msg)


class PedagogicalJudge:
    """Run all four metric judges over one question."""

    def __init__(self, session: Session, *, client: StructuredLLMClient | None = None) -> None:
        self._session = session
        self._client = client or get_structured_client()

    def evaluate(self, question: Question) -> PedagogicalEvaluation:
        """Return one evaluation, with a failed judge recorded rather than raised.

        A judge that cannot answer never blocks the question: the professor sees
        the metrics that did come back and reviews it anyway.
        """
        model = self._client.description
        try:
            context = build_judge_context(self._session, question)
        except (AdaptiveTrainerError, LookupError, TypeError, ValueError) as exc:
            detail = humanize_judge_error_detail(_error_detail(exc))
            return evaluation_from_metrics(
                [failed_metric(metric, detail=detail) for metric in JudgeMetricId],
                question_id=question.id,
                judge_model=model,
            )

        metrics = [self._run_metric(metric, context, question) for metric in JudgeMetricId]
        return evaluation_from_metrics(metrics, question_id=question.id, judge_model=model)

    def _run_metric(
        self, metric: JudgeMetricId, context: JudgeContext, question: Question
    ) -> MetricResult:
        """One judge, retried on transport and shape failures alike."""
        system = SYSTEM_PROMPT_FOR[metric]
        prompt = build_user_prompt(metric, context)
        last_detail = "unknown"
        for _ in range(JUDGE_MAX_ATTEMPTS):
            try:
                verdict = self._client.complete_structured(
                    system=system,
                    prompt=prompt,
                    response_model=RESPONSE_MODEL_FOR[metric],
                )
                return result_from_verdict(metric, verdict, question)
            except (LLMRequestError, MalformedModelOutputError) as exc:
                last_detail = humanize_judge_error_detail(str(exc.detail or exc))
        return failed_metric(metric, detail=last_detail)


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
    """Return a short professor-facing diagnostic for persisted failures."""
    detail = getattr(exc, "detail", None) or str(exc) or type(exc).__name__
    return str(detail)
