"""Professor review controls on the question detail page."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import QuestionStatus, ReviewDecision
from app.persistence.models import QuestionRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository


def _seed_question(session: Session) -> int:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Seed prompt",
            original_prompt="Seed prompt",
            reference_solution="true",
            original_reference_solution="true",
            tests="",
            original_tests="",
            status=QuestionStatus.VALIDATION_PASSED,
            generator_name="base",
            generator_version="1",
            spec_json='{"difficulty":"easy","question_type":"true_false"}',
        )
    )
    session.commit()
    return row.id


def test_detail_shows_spec_and_review_form(client: TestClient, session: Session) -> None:
    question_id = _seed_question(session)

    response = client.get(f"/questions/{question_id}")

    assert response.status_code == 200
    assert "Generation spec" in response.text
    assert "difficulty" in response.text
    assert "easy" in response.text
    assert 'name="decision"' in response.text
    assert "technically_incorrect" in response.text
    assert 'name="comment"' in response.text
    assert 'name="prompt"' in response.text
    assert ">Seed prompt</textarea>" in response.text


def test_post_approve(client: TestClient, session: Session) -> None:
    question_id = _seed_question(session)

    response = client.post(
        f"/questions/{question_id}/review",
        data={"decision": "approve", "comment": "Looks good"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/questions/{question_id}"
    session.expire_all()
    question = QuestionRepository(session).get(question_id)
    assert question.status == QuestionStatus.APPROVED
    review = ProfessorReviewRepository(session).list_recent()[0]
    assert review.decision == ReviewDecision.APPROVE
    assert review.comment == "Looks good"
    assert review.professor_id is None


def test_post_reject_multiple_reasons(client: TestClient, session: Session) -> None:
    question_id = _seed_question(session)

    response = client.post(
        f"/questions/{question_id}/review",
        data={
            "decision": "reject",
            "reasons": ["too_easy", "ambiguous"],
            "comment": "fix me",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    session.expire_all()
    review = ProfessorReviewRepository(session).list_recent()[0]
    assert review.decision == ReviewDecision.REJECT
    assert "too_easy" in (review.reasons_json or "")
    assert "ambiguous" in (review.reasons_json or "")


def test_post_edit_preserves_original(client: TestClient, session: Session) -> None:
    question_id = _seed_question(session)

    response = client.post(
        f"/questions/{question_id}/review",
        data={
            "decision": "edit",
            "reasons": ["poor_wording"],
            "prompt": "Improved prompt",
            "reference_solution": "true",
            "tests": "",
            "comment": "Wording",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    session.expire_all()
    question = QuestionRepository(session).get(question_id)
    assert question.prompt == "Improved prompt"
    assert question.original_prompt == "Seed prompt"
    assert question.status == QuestionStatus.APPROVED
