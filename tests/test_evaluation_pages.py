"""Question detail rendering for stored pedagogical evaluations."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionKind, QuestionType
from app.evaluation.rubric import JudgeDimensionId
from app.evaluation.schema import (
    AdvisoryStatus,
    DimensionEvaluation,
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
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
            subtopic_id=version.topics[0].subtopics[0].id,
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


def test_question_detail_shows_completed_pedagogical_evaluation(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    question_id = _seed_question(
        session,
        settings,
        PedagogicalEvaluation(
            status=PedagogicalEvalStatus.COMPLETED,
            overall_advisory_score=4.0,
            overall_advisory_status=AdvisoryStatus.STRONG,
            judge_model="fake/pedagogical-judge",
            dimensions=[
                DimensionEvaluation(
                    dimension=JudgeDimensionId.SOURCE_GROUNDING,
                    score=4,
                    confidence=0.9,
                    rationale="Grounded in the supplied section.",
                    issues=["Could cite a more specific example."],
                )
            ],
        ),
    )

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Deterministic checks" in response.text
    assert "LLM pedagogical evaluation" in response.text
    assert "Status: completed" in response.text
    assert "source_grounding:" in response.text
    assert "4/5" in response.text
    assert "Confidence: 0.9" in response.text
    assert "Grounded in the supplied section." in response.text
    assert "Could cite a more specific example." in response.text
    assert "Overall advisory mean:" in response.text
    assert "4.0" in response.text
    assert "(strong)" in response.text
    assert "summary only" in response.text
    assert "fake/pedagogical-judge" in response.text
    assert "pedagogical-judge@1" in response.text


def test_question_detail_shows_skipped_pedagogical_evaluation(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    question_id = _seed_question(
        session,
        settings,
        PedagogicalEvaluation(
            status=PedagogicalEvalStatus.SKIPPED,
            skip_reason="deterministic_failed",
            overall_advisory_status=AdvisoryStatus.SKIPPED,
        ),
    )

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Status: skipped" in response.text
    assert "Skipped: deterministic_failed" in response.text


def test_question_detail_shows_pedagogical_evaluation_error(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    question_id = _seed_question(
        session,
        settings,
        PedagogicalEvaluation(
            status=PedagogicalEvalStatus.ERROR,
            error_detail="Judge service unavailable.",
            overall_advisory_status=AdvisoryStatus.ERROR,
        ),
    )

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Status: error" in response.text
    assert "Judge service unavailable." in response.text
    assert "Error: Judge service unavailable." not in response.text


def test_question_detail_shows_an_empty_judge_history_panel(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    """A question judged before history existed still gets the panel, not an error."""
    question_id = _seed_question(
        session,
        settings,
        PedagogicalEvaluation(
            status=PedagogicalEvalStatus.SKIPPED,
            skip_reason="deterministic_failed",
            overall_advisory_status=AdvisoryStatus.SKIPPED,
        ),
    )

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

    question_id = _seed_question(
        session,
        settings,
        PedagogicalEvaluation(
            status=PedagogicalEvalStatus.COMPLETED,
            overall_advisory_score=4.0,
            overall_advisory_status=AdvisoryStatus.STRONG,
            judge_model="first/model",
        ),
    )
    for created_at, model, trigger in (
        (datetime.now(UTC) - timedelta(days=1), "first/model", EvaluationTrigger.GENERATION),
        (datetime.now(UTC), "second/model", EvaluationTrigger.BATCH_RERUN),
    ):
        record_evaluation(
            session,
            question_id,
            PedagogicalEvaluation(
                question_id=question_id,
                status=PedagogicalEvalStatus.COMPLETED,
                overall_advisory_score=4.0,
                overall_advisory_status=AdvisoryStatus.STRONG,
                judge_model=model,
                created_at=created_at,
            ),
            run_id=f"run-{model}",
            trigger=trigger,
        )
    session.commit()

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Judge history" in response.text
    assert "batch_rerun" in response.text
    # Newest first: the re-run row is rendered above the generation row.
    assert response.text.index("second/model") < response.text.index("first/model")
    assert "(current)" in response.text


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
