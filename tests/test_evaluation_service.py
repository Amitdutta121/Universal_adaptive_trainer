"""The four metric judges: pass derivation, retries, and partial failure."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from llm_fakes import FlakyJudgeClient, MetricJudgeClient, RaisingJudgeClient
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import (
    Difficulty,
    JudgeGate,
    JudgeMetricId,
    QuestionType,
    RejectionReason,
)
from app.domain.questions import Question
from app.errors import LLMRequestError, MalformedModelOutputError
from app.evaluation.prompts import build_user_prompt
from app.evaluation.schema import MetricStatus, PedagogicalEvalStatus
from app.evaluation.service import JUDGE_MAX_ATTEMPTS, PedagogicalJudge, build_judge_context
from app.ingestion import BookImportService

TAXONOMY = (
    b'{"schema_version":"1","label":"Python","topics":['
    b'{"name":"Output","subtopics":['
    b'{"name":"Printing","description":"print()"},'
    b'{"name":"Formatting","description":"f-strings"}]},'
    b'{"name":"Loops","subtopics":[{"name":"For loops","description":"for"}]}]}'
)


def _seed_question(session: Session, settings: Any) -> Question:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json", data=TAXONOMY
    )
    session.commit()
    section = book.chapters[0].sections[0]
    topic = version.topics[0]
    return Question(
        id=1,
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[topic.subtopics[0].id],
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        prompt="What is printed?",
        reference_solution="3",
        content={
            "prompt": "What is printed?",
            "code": "print(3)",
            "expected_output": "3",
            "sources": [{"section_id": section.id, "citation": "x"}],
        },
        spec={
            "curriculum_version_id": version.id,
            "question_type": "output_prediction",
            "difficulty": "easy",
            "source_section_ids": [section.id],
        },
    )


def _agreeing_client(question: Question) -> MetricJudgeClient:
    return MetricJudgeClient(
        topic_id=question.topic_id or 0,
        subtopic_ids=list(question.subtopic_ids),
        difficulty=question.difficulty,
    )


def test_all_metrics_agreeing_approves(session: Session, settings: Any) -> None:
    question = _seed_question(session, settings)
    client = _agreeing_client(question)

    result = PedagogicalJudge(session, client=client).evaluate(question)

    assert result.status is PedagogicalEvalStatus.COMPLETED
    assert result.gate is JudgeGate.APPROVED
    assert client.calls == len(JudgeMetricId)
    assert result.judge_model == "fake/judge-model"
    assert all(metric.passed for metric in result.metrics)
    assert all(metric.rationale for metric in result.metrics)


def test_one_failing_metric_needs_review(session: Session, settings: Any) -> None:
    question = _seed_question(session, settings)
    client = _agreeing_client(question)
    client.difficulty = Difficulty.HARD

    result = PedagogicalJudge(session, client=client).evaluate(question)

    assert result.gate is JudgeGate.NEEDS_REVIEW
    difficulty = result.metric(JudgeMetricId.DIFFICULTY)
    assert difficulty is not None
    assert difficulty.passed is False
    assert difficulty.proposed_difficulty is Difficulty.HARD


def test_every_metric_failing_rejects(session: Session, settings: Any) -> None:
    question = _seed_question(session, settings)
    client = MetricJudgeClient(
        topic_id=(question.topic_id or 0) + 100,
        subtopic_ids=[999],
        difficulty=Difficulty.HARD,
        issue_codes=[RejectionReason.AMBIGUOUS],
        should_have_generated=False,
    )

    result = PedagogicalJudge(session, client=client).evaluate(question)

    assert result.gate is JudgeGate.REJECT
    assert not any(metric.passed for metric in result.metrics)


def test_subtopic_metric_ignores_order(session: Session, settings: Any) -> None:
    question = _seed_question(session, settings)
    question = question.model_copy(update={"subtopic_ids": [2, 1]})
    client = MetricJudgeClient(
        topic_id=question.topic_id or 0,
        subtopic_ids=[1, 2],
        difficulty=question.difficulty,
    )

    result = PedagogicalJudge(session, client=client).evaluate(question)

    subtopic = result.metric(JudgeMetricId.SUBTOPIC)
    assert subtopic is not None
    assert subtopic.passed is True


def test_issue_codes_are_reported_with_the_failure(session: Session, settings: Any) -> None:
    question = _seed_question(session, settings)
    client = _agreeing_client(question)
    client.issue_codes = [RejectionReason.POOR_WORDING]
    client.custom_issue = "  the stem repeats itself  "

    result = PedagogicalJudge(session, client=client).evaluate(question)

    issues = result.metric(JudgeMetricId.ISSUES)
    assert issues is not None
    assert issues.passed is False
    assert issues.issue_codes == [RejectionReason.POOR_WORDING]
    assert issues.custom_issue == "the stem repeats itself"


def test_each_judge_retries_then_succeeds(session: Session, settings: Any) -> None:
    question = _seed_question(session, settings)
    client = FlakyJudgeClient(
        failures_per_metric=2,
        error=MalformedModelOutputError("bad json", detail="nope"),
        topic_id=question.topic_id or 0,
        subtopic_ids=list(question.subtopic_ids),
        difficulty=question.difficulty,
    )

    result = PedagogicalJudge(session, client=client).evaluate(question)

    assert result.status is PedagogicalEvalStatus.COMPLETED
    assert result.gate is JudgeGate.APPROVED


def test_all_judges_failing_gives_no_gate(session: Session, settings: Any) -> None:
    client = RaisingJudgeClient(LLMRequestError("down", detail="503"))
    question = _seed_question(session, settings)

    result = PedagogicalJudge(session, client=client).evaluate(question)

    assert result.status is PedagogicalEvalStatus.ERROR
    assert result.gate is None
    assert client.calls == JUDGE_MAX_ATTEMPTS * len(JudgeMetricId)
    assert len(result.error_details) == len(JudgeMetricId)


def test_unloadable_context_fails_every_metric_without_calling(
    session: Session, settings: Any
) -> None:
    client = MetricJudgeClient()
    question = _seed_question(session, settings).model_copy(update={"topic_id": 999})

    result = PedagogicalJudge(session, client=client).evaluate(question)

    assert result.status is PedagogicalEvalStatus.ERROR
    assert result.gate is None
    assert client.calls == 0
    assert all(metric.status is MetricStatus.ERROR for metric in result.metrics)


def test_generatability_judge_is_never_shown_the_question(session: Session, settings: Any) -> None:
    """Its subject is the source material, so seeing the question would bias it."""
    question = _seed_question(session, settings)
    context = build_judge_context(session, question)

    payload = build_user_prompt(JudgeMetricId.GENERATABILITY, context)

    assert "What is printed?" not in payload
    assert "requested_difficulty" in payload
    assert "source_sections" in payload


def test_subtopic_judge_sees_the_whole_taxonomy(session: Session, settings: Any) -> None:
    question = _seed_question(session, settings)
    context = build_judge_context(session, question)

    payload = build_user_prompt(JudgeMetricId.SUBTOPIC, context)

    assert "For loops" in payload
    assert "claimed_taxonomy" in payload
