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

from app.domain.enums import QuestionStatus, RejectionReason, ReviewDecision
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


# --- the page -------------------------------------------------------------


def test_page_renders_the_next_question_and_its_verdict_form(
    client: TestClient, session: Session
) -> None:
    question = _question(session)

    response = client.get("/review")

    assert response.status_code == 200
    assert f'action="/review/{question.id}"' in response.text
    assert 'value="approve"' in response.text


def test_page_renders_a_fenced_snippet_as_code(client: TestClient, session: Session) -> None:
    """Multiple-choice drafts carry their snippet in the prompt; show it as code."""
    question = _question(session)
    question.prompt = "What does this do?\n```python\nage = 25\n```"
    session.commit()

    body = client.get("/review").text
    # The edit textarea deliberately keeps the raw prompt, so scope this to the
    # panel the professor reads from.
    shown = body.split('class="panel review-question"')[1].split("</section>")[0]

    assert '<pre class="detail">age = 25</pre>' in shown
    assert "What does this do?" in shown
    assert "```" not in shown


def test_page_keeps_the_judge_verdict_closed(client: TestClient, session: Session) -> None:
    """Anchoring the professor to the judge would invalidate the agreement figures."""
    _question(session, evaluation=_evaluation())

    body = client.get("/review").text

    assert "Show what the judge said" in body
    assert "<details open" not in body


def test_submitting_a_verdict_advances_to_the_next_question(
    client: TestClient, session: Session
) -> None:
    first = _question(session)
    second = _question(session)

    response = client.post(
        f"/review/{first.id}", data={"decision": "approve", "mode": "all"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/review?after={first.id}&mode=all"
    assert f'action="/review/{second.id}"' in client.get(response.headers["location"]).text


def test_submitting_a_verdict_records_it(client: TestClient, session: Session) -> None:
    question = _question(session)

    client.post(f"/review/{question.id}", data={"decision": "approve", "mode": "all"})

    session.expire_all()
    stored = QuestionRepository(session).get(question.id)
    assert [review.decision for review in stored.reviews] == [ReviewDecision.APPROVE]


def test_submitting_a_reject_carries_its_reasons(client: TestClient, session: Session) -> None:
    question = _question(session)

    client.post(
        f"/review/{question.id}",
        data={"decision": "reject", "reasons": ["too_easy"], "comment": "Trivial.", "mode": "all"},
    )

    session.expire_all()
    review = QuestionRepository(session).get(question.id).reviews[0]
    assert review.reasons == [RejectionReason.TOO_EASY]
    assert review.comment == "Trivial."


def test_a_rejected_verdict_without_reasons_re_offers_the_same_question(
    client: TestClient, session: Session
) -> None:
    """The cursor must not advance past a verdict the domain refused to record."""
    question = _question(session)
    _question(session)

    response = client.post(f"/review/{question.id}", data={"decision": "reject", "mode": "all"})

    assert response.status_code == 422
    assert f'action="/review/{question.id}"' in response.text
    session.expire_all()
    assert QuestionRepository(session).get(question.id).reviews == []


def test_page_preserves_the_mode_across_a_submission(client: TestClient, session: Session) -> None:
    question = _question(session, evaluation=_evaluation())

    response = client.post(
        f"/review/{question.id}",
        data={"decision": "approve", "mode": "scoreable"},
        follow_redirects=False,
    )

    assert response.headers["location"].endswith("mode=scoreable")


def test_page_falls_back_to_all_for_an_unknown_mode(client: TestClient, session: Session) -> None:
    question = _question(session)

    response = client.get("/review", params={"mode": "nonsense"})

    assert response.status_code == 200
    assert f'action="/review/{question.id}"' in response.text


def test_page_offers_a_restart_when_the_pass_ends_with_work_left(
    client: TestClient, session: Session
) -> None:
    question = _question(session)

    body = client.get("/review", params={"after": question.id}).text

    assert "Start again from the first unreviewed question" in body


def test_page_reports_an_empty_bank_without_erroring(client: TestClient) -> None:
    response = client.get("/review")

    assert response.status_code == 200
    assert "Nothing left to review" in response.text
