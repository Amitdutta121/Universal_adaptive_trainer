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
            spec_json=f'{{"source_section_ids":[{book.chapters[0].sections[0].id}]}}',
            content_json='{"code":"print(3)","expected_output":"3"}',
            pedagogical_eval_json=evaluation.model_dump_json(),
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
