"""Judge calibration: label mapping, pairing, metrics and the endpoint.

Guards ADR-029. The rule most easily lost in a later change is that the *first*
professor review is the one compared, so it is asserted through the real review
workflow rather than by inserting rows.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.calibration import (
    MIN_INFORMATIVE_SAMPLE,
    CalibrationLabel,
    CalibrationPair,
    build_calibration_pairs,
    build_calibration_report,
    judge_label,
    metrics_from_pairs,
    professor_label,
)
from app.domain.enums import QuestionStatus, RejectionReason, ReviewDecision
from app.evaluation import AdvisoryStatus, PedagogicalEvalStatus, PedagogicalEvaluation
from app.feedback import submit_review
from app.persistence.models import QuestionRow
from app.persistence.repositories import QuestionRepository

ACCEPT = CalibrationLabel.ACCEPT
NEEDS_REVIEW = CalibrationLabel.NEEDS_REVIEW


def _evaluation(
    advisory: AdvisoryStatus,
    *,
    status: PedagogicalEvalStatus = PedagogicalEvalStatus.COMPLETED,
) -> PedagogicalEvaluation:
    return PedagogicalEvaluation(
        status=status,
        overall_advisory_score=4.0,
        overall_advisory_status=advisory,
        judge_model="fake/pedagogical-judge",
    )


def _question(session: Session, *, evaluation: object | None) -> QuestionRow:
    """A reviewable question carrying whatever blob the test wants stored."""
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
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=evaluation,
        )
    )
    session.commit()
    return row


def _judged(session: Session, advisory: AdvisoryStatus, decision: ReviewDecision) -> QuestionRow:
    """A question with one stored evaluation and one professor review."""
    question = _question(session, evaluation=_evaluation(advisory).model_dump(mode="json"))
    submit_review(
        session,
        question_id=question.id,
        decision=decision,
        reasons=[RejectionReason.TOO_EASY] if decision is ReviewDecision.REJECT else None,
        prompt="Write a nested loop." if decision is ReviewDecision.EDIT else None,
        reference_solution="pass" if decision is ReviewDecision.EDIT else None,
        tests="assert True" if decision is ReviewDecision.EDIT else None,
    )
    session.commit()
    return question


def _pairs(*labels: tuple[CalibrationLabel, CalibrationLabel]) -> list[CalibrationPair]:
    return [
        CalibrationPair(question_id=index + 1, judge=judge, professor=professor)
        for index, (judge, professor) in enumerate(labels)
    ]


# ------------------------------------------------------------------ label mapping


@pytest.mark.parametrize(
    ("advisory", "expected"),
    [
        (AdvisoryStatus.STRONG, ACCEPT),
        (AdvisoryStatus.ADEQUATE, NEEDS_REVIEW),
        (AdvisoryStatus.WEAK, NEEDS_REVIEW),
        (AdvisoryStatus.UNCERTAIN, NEEDS_REVIEW),
        (AdvisoryStatus.SKIPPED, None),
        (AdvisoryStatus.ERROR, None),
    ],
)
def test_every_judge_advisory_status_maps_as_documented(
    advisory: AdvisoryStatus, expected: CalibrationLabel | None
) -> None:
    assert judge_label(_evaluation(advisory)) is expected


def test_the_mapping_covers_every_advisory_status_that_exists() -> None:
    """A new band must not fall through to ``NEEDS_REVIEW`` unnoticed."""
    assert {status.value for status in AdvisoryStatus} == {
        "strong",
        "adequate",
        "weak",
        "uncertain",
        "skipped",
        "error",
    }


@pytest.mark.parametrize("status", [PedagogicalEvalStatus.SKIPPED, PedagogicalEvalStatus.ERROR])
def test_an_evaluation_that_never_completed_is_unusable_however_it_scored(
    status: PedagogicalEvalStatus,
) -> None:
    # A `strong` band on a non-completed record is stale data, not a prediction.
    assert judge_label(_evaluation(AdvisoryStatus.STRONG, status=status)) is None


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (ReviewDecision.APPROVE, ACCEPT),
        (ReviewDecision.EDIT, NEEDS_REVIEW),
        (ReviewDecision.REJECT, NEEDS_REVIEW),
    ],
)
def test_every_professor_decision_maps_as_documented(
    decision: ReviewDecision, expected: CalibrationLabel
) -> None:
    assert professor_label(decision) is expected


def test_the_mapping_covers_every_review_decision_that_exists() -> None:
    assert {decision.value for decision in ReviewDecision} == {"approve", "reject", "edit"}


# ----------------------------------------------------------------------- metrics


def test_metrics_over_a_known_mix() -> None:
    report = metrics_from_pairs(
        _pairs(
            (ACCEPT, ACCEPT),
            (ACCEPT, ACCEPT),
            (ACCEPT, NEEDS_REVIEW),
            (NEEDS_REVIEW, NEEDS_REVIEW),
            (NEEDS_REVIEW, ACCEPT),
        )
    )

    assert report.n == 5
    assert report.judge_accept_count == 3
    # Three of five labels match: two accept/accept and one needs_review pair.
    assert report.agreement == 0.6
    assert report.auto_accept_precision == 0.6667
    assert report.unsafe_auto_accept_rate == 0.3333


def test_a_perfect_judge_scores_one_and_a_reversed_one_scores_zero() -> None:
    perfect = metrics_from_pairs(_pairs((ACCEPT, ACCEPT), (NEEDS_REVIEW, NEEDS_REVIEW)))
    reversed_judge = metrics_from_pairs(_pairs((ACCEPT, NEEDS_REVIEW), (NEEDS_REVIEW, ACCEPT)))

    assert perfect.agreement == 1.0
    assert perfect.auto_accept_precision == 1.0
    assert perfect.unsafe_auto_accept_rate == 0.0
    assert reversed_judge.agreement == 0.0
    assert reversed_judge.auto_accept_precision == 0.0
    assert reversed_judge.unsafe_auto_accept_rate == 1.0


def test_no_pairs_at_all_reports_null_rather_than_zero() -> None:
    report = metrics_from_pairs([])

    assert report.n == 0
    assert report.judge_accept_count == 0
    assert report.agreement is None
    assert report.auto_accept_precision is None
    assert report.unsafe_auto_accept_rate is None


def test_no_judge_accepts_nulls_only_the_auto_accept_rates() -> None:
    report = metrics_from_pairs(_pairs((NEEDS_REVIEW, ACCEPT), (NEEDS_REVIEW, NEEDS_REVIEW)))

    assert report.judge_accept_count == 0
    assert report.agreement == 0.5
    assert report.auto_accept_precision is None
    assert report.unsafe_auto_accept_rate is None


# --------------------------------------------------------------------- pairing


def test_pairs_are_built_from_stored_evaluations_and_reviews(session: Session) -> None:
    strong = _judged(session, AdvisoryStatus.STRONG, ReviewDecision.APPROVE)
    weak = _judged(session, AdvisoryStatus.WEAK, ReviewDecision.REJECT)

    pairs = build_calibration_pairs(session)

    assert [(pair.question_id, pair.judge, pair.professor) for pair in pairs] == [
        (strong.id, ACCEPT, ACCEPT),
        (weak.id, NEEDS_REVIEW, NEEDS_REVIEW),
    ]


def test_an_edit_then_approve_counts_once_as_needs_review(session: Session) -> None:
    """The judge scored the generated question, which the professor had to fix."""
    question = _judged(session, AdvisoryStatus.STRONG, ReviewDecision.EDIT)
    submit_review(session, question_id=question.id, decision=ReviewDecision.APPROVE)
    session.commit()

    pairs = build_calibration_pairs(session)

    assert len(pairs) == 1
    assert pairs[0].professor is NEEDS_REVIEW
    report = build_calibration_report(session)
    assert report.n == 1
    assert report.judge_accept_count == 1
    assert report.auto_accept_precision == 0.0
    assert report.unsafe_auto_accept_rate == 1.0


@pytest.mark.parametrize(
    ("advisory", "status"),
    [
        (AdvisoryStatus.SKIPPED, PedagogicalEvalStatus.SKIPPED),
        (AdvisoryStatus.ERROR, PedagogicalEvalStatus.ERROR),
        (AdvisoryStatus.STRONG, PedagogicalEvalStatus.SKIPPED),
    ],
)
def test_unusable_evaluations_are_left_out_of_the_report(
    session: Session, advisory: AdvisoryStatus, status: PedagogicalEvalStatus
) -> None:
    question = _question(
        session, evaluation=_evaluation(advisory, status=status).model_dump(mode="json")
    )
    submit_review(session, question_id=question.id, decision=ReviewDecision.APPROVE)
    session.commit()

    assert build_calibration_pairs(session) == []
    assert build_calibration_report(session).n == 0


def test_a_question_with_no_review_is_not_a_pair(session: Session) -> None:
    _question(session, evaluation=_evaluation(AdvisoryStatus.STRONG).model_dump(mode="json"))

    assert build_calibration_pairs(session) == []


def test_a_question_with_no_evaluation_is_not_a_pair(session: Session) -> None:
    question = _question(session, evaluation=None)
    submit_review(session, question_id=question.id, decision=ReviewDecision.APPROVE)
    session.commit()

    assert build_calibration_pairs(session) == []


@pytest.mark.parametrize(
    "blob",
    [
        {},
        {"status": "completed"},
        {"status": "completed", "overall_advisory_status": "excellent"},
        {"status": "invented", "overall_advisory_status": "strong"},
        "not an object at all",
    ],
)
def test_a_stored_evaluation_that_no_longer_validates_is_skipped(
    session: Session, caplog: pytest.LogCaptureFixture, blob: object
) -> None:
    stale = _question(session, evaluation=blob)
    submit_review(session, question_id=stale.id, decision=ReviewDecision.APPROVE)
    usable = _judged(session, AdvisoryStatus.STRONG, ReviewDecision.APPROVE)
    session.commit()

    with caplog.at_level(logging.WARNING, logger="app.calibration.service"):
        pairs = build_calibration_pairs(session)

    assert [pair.question_id for pair in pairs] == [usable.id]
    assert f"Skipping question {stale.id}" in caplog.text


# -------------------------------------------------------------------- endpoint


def test_results_on_an_empty_database_report_nulls(client: TestClient) -> None:
    response = client.get("/api/calibration/results")

    assert response.status_code == 200
    assert response.json() == {
        "n": 0,
        "judge_accept_count": 0,
        "agreement": None,
        "auto_accept_precision": None,
        "unsafe_auto_accept_rate": None,
    }


def test_results_report_the_stored_agreement(client: TestClient, session: Session) -> None:
    _judged(session, AdvisoryStatus.STRONG, ReviewDecision.APPROVE)
    _judged(session, AdvisoryStatus.STRONG, ReviewDecision.REJECT)
    _judged(session, AdvisoryStatus.WEAK, ReviewDecision.REJECT)
    # Neither of these may reach the denominator.
    _judged(session, AdvisoryStatus.SKIPPED, ReviewDecision.APPROVE)
    _question(session, evaluation=_evaluation(AdvisoryStatus.STRONG).model_dump(mode="json"))

    payload = client.get("/api/calibration/results").json()

    assert payload == {
        "n": 3,
        "judge_accept_count": 2,
        "agreement": 0.6667,
        "auto_accept_precision": 0.5,
        "unsafe_auto_accept_rate": 0.5,
    }


def test_pairs_expose_the_evidence_behind_the_figures(client: TestClient, session: Session) -> None:
    agreeing = _judged(session, AdvisoryStatus.STRONG, ReviewDecision.APPROVE)
    disagreeing = _judged(session, AdvisoryStatus.STRONG, ReviewDecision.REJECT)
    excluded = _judged(session, AdvisoryStatus.SKIPPED, ReviewDecision.APPROVE)

    payload = client.get("/api/calibration/pairs").json()

    assert payload["total"] == 2
    assert payload["pairs"] == [
        {
            "question_id": agreeing.id,
            "judge": "accept",
            "professor": "accept",
            "agrees": True,
        },
        {
            "question_id": disagreeing.id,
            "judge": "accept",
            "professor": "needs_review",
            "agrees": False,
        },
    ]
    assert excluded.id not in [pair["question_id"] for pair in payload["pairs"]]


def test_pairs_on_an_empty_database_are_empty(client: TestClient) -> None:
    assert client.get("/api/calibration/pairs").json() == {"pairs": [], "total": 0}


def test_results_are_read_only(client: TestClient, session: Session) -> None:
    """Calibration observes history; it must not add to what it measures."""
    _judged(session, AdvisoryStatus.STRONG, ReviewDecision.APPROVE)

    first = client.get("/api/calibration/results").json()
    second = client.get("/api/calibration/results").json()

    assert first == second
    assert client.get("/api/reviews").json()["total"] == 1
    assert client.post("/api/calibration/results").status_code == 405


def test_openapi_documents_the_calibration_endpoint(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/calibration/results" in schema["paths"]
    assert "/api/calibration/pairs" in schema["paths"]
    for path in ("/api/calibration/results", "/api/calibration/pairs"):
        assert set(schema["paths"][path]) == {"get"}, f"{path} must stay read-only"
    properties = schema["components"]["schemas"]["CalibrationResultsResponse"]["properties"]
    assert set(properties) == {
        "n",
        "judge_accept_count",
        "agreement",
        "auto_accept_precision",
        "unsafe_auto_accept_rate",
    }


# ------------------------------------------------------------------------ page


def test_the_feedback_page_states_an_honest_empty_calibration(client: TestClient) -> None:
    body = client.get("/feedback").text

    assert "Judge calibration" in body
    assert "No question has both a completed judge evaluation and a professor review yet" in body


def test_the_feedback_page_shows_the_figures_and_their_evidence(
    client: TestClient, session: Session
) -> None:
    agreeing = _judged(session, AdvisoryStatus.STRONG, ReviewDecision.APPROVE)
    disagreeing = _judged(session, AdvisoryStatus.STRONG, ReviewDecision.REJECT)

    body = client.get("/feedback").text

    # Two accepts, one confirmed: 50.0% precision and the same unsafe rate.
    assert "Auto-accept precision" in body
    assert "50.0%" in body
    assert "Unsafe auto-accept rate" in body
    # Every counted question is linked, so a figure can be traced to its rows.
    assert f'href="/questions/{agreeing.id}"' in body
    assert f'href="/questions/{disagreeing.id}"' in body
    assert "agree" in body
    assert "disagree" in body


def test_the_feedback_page_warns_that_a_small_sample_proves_nothing(
    client: TestClient, session: Session
) -> None:
    _judged(session, AdvisoryStatus.STRONG, ReviewDecision.APPROVE)

    body = client.get("/feedback").text

    assert "small sample" in body
    assert str(MIN_INFORMATIVE_SAMPLE) in body


def test_a_null_rate_renders_as_a_dash_rather_than_zero(
    client: TestClient, session: Session
) -> None:
    """No judge accept means no precision to report -- not a precision of zero."""
    _judged(session, AdvisoryStatus.WEAK, ReviewDecision.REJECT)

    body = client.get("/feedback").text

    for label in ("Auto-accept precision", "Unsafe auto-accept rate"):
        cell = body.split(f"{label}</dt>", 1)[1].split("</dd>", 1)[0]
        assert "—" in cell, f"{label} must render as a dash"
        assert "%" not in cell, f"{label} must not invent a percentage"
    # The rate that does have a denominator is still reported.
    assert "100.0% of 1" in body
