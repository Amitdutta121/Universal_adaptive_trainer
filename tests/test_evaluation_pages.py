"""Question detail rendering for stored advisory reviews."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from fastapi.testclient import TestClient
from llm_fakes import judged, metric_results
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import (
    Difficulty,
    JudgeMetricId,
    QuestionKind,
    QuestionType,
    RejectionReason,
)
from app.evaluation.schema import (
    IssuesVerdict,
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
    SubtopicVerdict,
    evaluation_from_metrics,
    result_from_issues,
    result_from_subtopic,
    skipped_evaluation,
)
from app.ingestion import BookImportService
from app.persistence.models import QuestionRow
from app.persistence.repositories import QuestionRepository


def _seed_question(
    session: Session,
    settings: Any,
    evaluation: PedagogicalEvaluation,
) -> int:
    book = BookImportService(session, settings).import_upload(
        filename="book.json",
        data=docs.to_bytes(docs.minimal()),
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Output","subtopics":[{"name":"Printing"}]}]}'
        ),
    )
    question = QuestionRepository(session).add(
        QuestionRow(
            curriculum_version_id=version.id,
            topic_id=version.topics[0].id,
            subtopic_ids=[version.topics[0].subtopics[0].id],
            kind=QuestionKind.DISCRETE,
            question_type=QuestionType.OUTPUT_PREDICTION,
            difficulty=Difficulty.EASY,
            prompt="What is printed?",
            reference_solution="3",
            spec={"source_section_ids": [book.chapters[0].sections[0].id]},
            content={"code": "print(3)", "expected_output": "3"},
            pedagogical_eval=evaluation.model_dump(mode="json"),
        )
    )
    session.commit()
    return question.id


def test_question_detail_shows_an_approved_review(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    question_id = _seed_question(session, settings, judged(judge_model="fake/pedagogical-judge"))

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Deterministic checks" in response.text
    assert "Advisory review" in response.text
    assert "Approved" in response.text
    assert "Subtopic tagging" in response.text
    assert "Could this chunk support the request" in response.text
    assert "fake/pedagogical-judge" in response.text
    assert "question-metrics@1" in response.text


def test_question_detail_shows_issue_codes_and_proposals(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    metrics = metric_results()
    metrics[0] = result_from_issues(
        IssuesVerdict(
            issue_codes=[RejectionReason.POOR_WORDING],
            custom_issue="The stem repeats itself.",
            rationale="Two clauses say the same thing.",
        )
    )
    metrics[1] = result_from_subtopic(
        SubtopicVerdict(topic_id=9, subtopic_ids=[41, 42], rationale="It is about loops."),
        claimed=[1],
        topic_id=1,
    )
    evaluation = evaluation_from_metrics(metrics, question_id=None, judge_model="m")
    question_id = _seed_question(session, settings, evaluation)

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Needs review" in response.text
    assert "Poor wording" in response.text
    assert "The stem repeats itself." in response.text
    assert "Two clauses say the same thing." in response.text
    assert "Would tag it topic 9" in response.text
    assert "41, 42" in response.text


def test_question_detail_shows_a_skipped_review(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    question_id = _seed_question(session, settings, skipped_evaluation(question_id=None))

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "No suggestion" in response.text
    assert "Not reviewed: deterministic_failed" in response.text


def test_question_detail_names_the_reviewer_that_failed(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    """A failed reviewer is shown as unanswered, and no gate is invented."""
    evaluation = judged(missing={JudgeMetricId.DIFFICULTY})
    question_id = _seed_question(session, settings, evaluation)

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "status: partial" in response.text
    assert "This reviewer did not answer." in response.text
    assert "reviewer unavailable" in response.text
    assert "No suggestion" in response.text
    assert "only derived when all four reviewers answer" in response.text


def test_question_detail_shows_an_empty_judge_history_panel(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    """A question judged before history existed still gets the panel, not an error."""
    question_id = _seed_question(session, settings, skipped_evaluation(question_id=None))

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Judge history" in response.text
    assert "No evaluation history has been recorded" in response.text


def test_question_detail_lists_retained_evaluations_newest_first(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.domain.enums import EvaluationTrigger
    from app.evaluation import record_evaluation

    question_id = _seed_question(session, settings, judged(judge_model="first/model"))
    for created_at, model, trigger in (
        (datetime.now(UTC) - timedelta(days=1), "first/model", EvaluationTrigger.GENERATION),
        (datetime.now(UTC), "second/model", EvaluationTrigger.BATCH_RERUN),
    ):
        evaluation = judged(question_id=question_id, judge_model=model)
        record_evaluation(
            session,
            question_id,
            evaluation.model_copy(update={"created_at": created_at}),
            run_id=f"run-{model}",
            trigger=trigger,
        )
    session.commit()

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Judge history" in response.text
    assert "batch_rerun" in response.text
    assert "4/4" in response.text
    # Newest first: the re-run row is rendered above the generation row.
    assert response.text.index("second/model") < response.text.index("first/model")
    assert "(current)" in response.text


def test_evaluation_status_is_still_reported(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    question_id = _seed_question(session, settings, judged())

    response = client.get(f"/questions/{question_id}")

    assert f"status: {PedagogicalEvalStatus.COMPLETED.value}" in response.text


def test_questions_page_offers_a_bulk_rerun_and_reports_it_disabled(
    client: TestClient,
) -> None:
    """Test settings leave the batch judge off, so the page must say so."""
    response = client.get("/questions")

    assert response.status_code == 200
    assert "Bulk judge re-run" in response.text
    assert "JUDGE_BATCH_ENABLED" in response.text
    assert "No judge re-run has been submitted yet." in response.text


def test_submitting_a_rerun_from_the_page_reports_the_configuration_error(
    client: TestClient,
) -> None:
    response = client.post("/questions/judge-runs")

    assert response.status_code == 500
    assert "Bulk judge re-run is disabled." in response.text
    # Stays on the questions page as an inline banner, not a whole error page.
    assert "Question bank" in response.text
