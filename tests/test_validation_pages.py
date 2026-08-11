"""Professor page rendering for stored automatic validation reports."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionKind, QuestionType
from app.domain.questions import QuestionCheck, QuestionValidationReport
from app.ingestion import BookImportService
from app.persistence.models import QuestionRow
from app.persistence.repositories import QuestionRepository


def _seed_question(
    session: Session,
    settings: Any,
    *,
    check_passed: bool,
) -> int:
    book = BookImportService(session, settings).import_upload(
        filename="book.json",
        data=docs.to_bytes(docs.think_python()),
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
        ),
    )
    report = QuestionValidationReport(
        checks=[
            QuestionCheck(
                name="approved_taxonomy_ids",
                passed=check_passed,
                detail="Approved curriculum IDs",
            )
        ]
    )
    question = QuestionRepository(session).add(
        QuestionRow(
            curriculum_version_id=version.id,
            topic_id=version.topics[0].id,
            subtopic_id=version.topics[0].subtopics[0].id,
            kind=QuestionKind.DISCRETE,
            question_type=QuestionType.TRUE_FALSE,
            difficulty=Difficulty.EASY,
            prompt="Strings are immutable.",
            reference_solution="true",
            spec_json=f'{{"source_section_ids":[{book.chapters[0].sections[0].id}]}}',
            content_json='{"correct_answer":true,"explanation":"Strings cannot be changed."}',
            validation_report_json=report.model_dump_json(),
        )
    )
    session.commit()
    return question.id


def test_question_detail_shows_passing_automatic_checks(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    question_id = _seed_question(session, settings, check_passed=True)

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Automatic Checks" in response.text
    assert "Approved curriculum IDs" in response.text
    assert "✓" in response.text


def test_question_detail_shows_failing_automatic_checks(
    client: TestClient,
    session: Session,
    settings: Any,
) -> None:
    question_id = _seed_question(session, settings, check_passed=False)

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Automatic Checks" in response.text
    assert "✗" in response.text
