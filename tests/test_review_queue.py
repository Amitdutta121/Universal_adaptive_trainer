"""The review queue: what it offers next, and how a verdict advances it.

The queue exists so a professor can review a hundred questions in one sitting,
so these tests are mostly about movement -- that submitting advances, that
skipping advances, and that neither one loses a question or offers one twice.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from llm_fakes import metric_results
from sqlalchemy.orm import Session

from app.domain.enums import QuestionStatus, ReviewDecision
from app.evaluation import PedagogicalEvalStatus, PedagogicalEvaluation
from app.feedback import submit_review
from app.persistence.models import QuestionRow
from app.persistence.repositories import QuestionRepository


def _evaluation(
    status: PedagogicalEvalStatus = PedagogicalEvalStatus.COMPLETED,
) -> dict[str, object]:
    return PedagogicalEvaluation(
        status=status,
        metrics=metric_results() if status is PedagogicalEvalStatus.COMPLETED else [],
        judge_model="synthetic/judge",
    ).model_dump(mode="json")


def _question(
    session: Session,
    *,
    evaluation: object | None = None,
    status: QuestionStatus = QuestionStatus.VALIDATION_PASSED,
) -> QuestionRow:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Write a loop.",
            original_prompt="Write a loop.",
            reference_solution="pass",
            original_reference_solution="pass",
            tests="assert True",
            original_tests="assert True",
            generator_name="base-gen",
            generator_version="1",
            status=status,
            pedagogical_eval=evaluation,
        )
    )
    session.commit()
    return row


def _review(session: Session, question: QuestionRow) -> None:
    submit_review(session, question_id=question.id, decision=ReviewDecision.APPROVE)
    session.commit()


def _queue(client: TestClient, **params: object) -> dict:
    response = client.get("/api/questions/review-queue", params=params)
    assert response.status_code == 200
    return response.json()


# --- what the queue offers ------------------------------------------------


def test_queue_offers_the_lowest_unreviewed_question(client: TestClient, session: Session) -> None:
    first = _question(session)
    _question(session)

    assert _queue(client)["question"]["question"]["id"] == first.id


def test_queue_skips_questions_that_already_have_a_verdict(
    client: TestClient, session: Session
) -> None:
    reviewed = _question(session)
    pending = _question(session)
    _review(session, reviewed)

    assert _queue(client)["question"]["question"]["id"] == pending.id


def test_queue_is_empty_once_every_question_is_reviewed(
    client: TestClient, session: Session
) -> None:
    _review(session, _question(session))

    payload = _queue(client)

    assert payload["question"] is None
    assert payload["remaining"] == 0


def test_queue_reports_progress_counts(client: TestClient, session: Session) -> None:
    _review(session, _question(session))
    _question(session)
    _question(session)

    payload = _queue(client)

    assert (payload["total"], payload["reviewed"], payload["remaining"]) == (3, 1, 2)


def test_queue_never_offers_a_question_that_failed_validation(
    client: TestClient, session: Session
) -> None:
    """A deterministic fault has no verdict left to solicit (ADR-032)."""
    _question(session, status=QuestionStatus.VALIDATION_FAILED)
    usable = _question(session)

    payload = _queue(client)

    assert payload["question"]["question"]["id"] == usable.id
    # And it is excluded from the total too, so a finished pass reads as finished
    # rather than stalling on a question the queue will never offer.
    assert (payload["total"], payload["remaining"]) == (1, 1)


def test_a_finished_pass_reaches_zero_despite_failed_questions(
    client: TestClient, session: Session
) -> None:
    _question(session, status=QuestionStatus.VALIDATION_FAILED)
    _review(session, _question(session))

    payload = _queue(client)

    assert payload["question"] is None
    assert (payload["total"], payload["reviewed"], payload["remaining"]) == (1, 1, 0)


def test_review_queue_path_is_not_parsed_as_a_question_id(client: TestClient) -> None:
    """The literal route must win over ``/questions/{question_id}``."""
    assert client.get("/api/questions/review-queue").status_code == 200


# --- the cursor -----------------------------------------------------------


def test_after_moves_past_the_named_question(client: TestClient, session: Session) -> None:
    first = _question(session)
    second = _question(session)

    assert _queue(client, after=first.id)["question"]["question"]["id"] == second.id


def test_cursor_past_the_last_question_returns_none_but_still_counts_remaining(
    client: TestClient, session: Session
) -> None:
    only = _question(session)

    payload = _queue(client, after=only.id)

    # Skipped, not finished: the professor is at the end of a pass with work left.
    assert payload["question"] is None
    assert payload["remaining"] == 1


# --- scoreable mode -------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [PedagogicalEvalStatus.SKIPPED, PedagogicalEvalStatus.ERROR],
)
def test_scoreable_mode_ignores_evaluations_that_never_reached_a_verdict(
    client: TestClient, session: Session, status: PedagogicalEvalStatus
) -> None:
    _question(session, evaluation=_evaluation(status))
    judged = _question(session, evaluation=_evaluation())

    assert _queue(client, mode="scoreable")["question"]["question"]["id"] == judged.id


def test_scoreable_mode_ignores_questions_with_no_evaluation(
    client: TestClient, session: Session
) -> None:
    _question(session)
    judged = _question(session, evaluation=_evaluation())

    assert _queue(client, mode="scoreable")["question"]["question"]["id"] == judged.id


def test_scoreable_mode_ignores_an_evaluation_that_no_longer_validates(
    client: TestClient, session: Session
) -> None:
    _question(session, evaluation={"status": "completed", "metrics": "??"})
    judged = _question(session, evaluation=_evaluation())

    assert _queue(client, mode="scoreable")["question"]["question"]["id"] == judged.id


def test_scoreable_remaining_counts_the_pool_not_the_cursor(
    client: TestClient, session: Session
) -> None:
    first = _question(session, evaluation=_evaluation())
    _question(session, evaluation=_evaluation())
    _question(session)

    # Moving the cursor past one of them must not shrink the reported pool.
    assert _queue(client, after=first.id)["scoreable_remaining"] == 2


def test_all_mode_offers_questions_the_judge_never_scored(
    client: TestClient, session: Session
) -> None:
    unjudged = _question(session)

    assert _queue(client, mode="all")["question"]["question"]["id"] == unjudged.id
