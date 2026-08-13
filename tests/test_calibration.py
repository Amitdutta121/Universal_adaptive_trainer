"""Judge calibration: label mapping, pairing, metrics and the endpoint.

Guards ADR-029. The rule most easily lost in a later change is that the *first*
professor review is the one compared, so it is asserted through the real review
workflow rather than by inserting rows.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from llm_fakes import metric_results
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
from app.domain.enums import (
    JudgeGate,
    JudgeMetricId,
    QuestionStatus,
    RejectionReason,
    ReviewDecision,
)
from app.evaluation import PedagogicalEvalStatus, PedagogicalEvaluation
from app.feedback import submit_review
from app.persistence.models import QuestionRow
from app.persistence.repositories import QuestionRepository

ACCEPT = CalibrationLabel.ACCEPT
NEEDS_REVIEW = CalibrationLabel.NEEDS_REVIEW


def _evaluation(
    gate: JudgeGate | None = JudgeGate.APPROVED,
    *,
    status: PedagogicalEvalStatus = PedagogicalEvalStatus.COMPLETED,
    failing: set[JudgeMetricId] | None = None,
) -> PedagogicalEvaluation:
    """A stored evaluation whose gate is what the test says it is."""
    if failing is None:
        failing = _failing_for(gate)
    return PedagogicalEvaluation(
        status=status,
        gate=gate,
        metrics=metric_results(failing=failing),
        judge_model="fake/pedagogical-judge",
    )


def _failing_for(gate: JudgeGate | None) -> set[JudgeMetricId]:
    if gate is JudgeGate.REJECT:
        return set(JudgeMetricId)
    if gate is JudgeGate.NEEDS_REVIEW:
        return {JudgeMetricId.DIFFICULTY}
    return set()


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


def _judged(
    session: Session,
    gate: JudgeGate | None,
    decision: ReviewDecision,
    *,
    failing: set[JudgeMetricId] | None = None,
) -> QuestionRow:
    """A question with one stored evaluation and one professor review."""
    question = _question(
        session, evaluation=_evaluation(gate, failing=failing).model_dump(mode="json")
    )
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
    ("gate", "expected"),
    [
        (JudgeGate.APPROVED, ACCEPT),
        (JudgeGate.NEEDS_REVIEW, NEEDS_REVIEW),
        (JudgeGate.REJECT, NEEDS_REVIEW),
        (None, None),
    ],
)
def test_every_judge_gate_maps_as_documented(
    gate: JudgeGate | None, expected: CalibrationLabel | None
) -> None:
    assert judge_label(_evaluation(gate)) is expected


def test_the_mapping_covers_every_gate_that_exists() -> None:
    """A new gate must not fall through to ``NEEDS_REVIEW`` unnoticed."""
    assert {gate.value for gate in JudgeGate} == {"approved", "needs_review", "reject"}


@pytest.mark.parametrize(
    "status",
    [
        PedagogicalEvalStatus.SKIPPED,
        PedagogicalEvalStatus.ERROR,
        PedagogicalEvalStatus.PARTIAL,
    ],
)
def test_an_evaluation_that_never_completed_is_unusable_however_it_gated(
    status: PedagogicalEvalStatus,
) -> None:
    """A gate on a non-completed record is stale data, not a prediction."""
    assert judge_label(_evaluation(JudgeGate.APPROVED, status=status)) is None


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
    strong = _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    weak = _judged(session, JudgeGate.NEEDS_REVIEW, ReviewDecision.REJECT)

    pairs = build_calibration_pairs(session)

    assert [(pair.question_id, pair.judge, pair.professor) for pair in pairs] == [
        (strong.id, ACCEPT, ACCEPT),
        (weak.id, NEEDS_REVIEW, NEEDS_REVIEW),
    ]


def test_an_edit_then_approve_counts_once_as_needs_review(session: Session) -> None:
    """The judge scored the generated question, which the professor had to fix."""
    question = _judged(session, JudgeGate.APPROVED, ReviewDecision.EDIT)
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
    ("gate", "status"),
    [
        (None, PedagogicalEvalStatus.SKIPPED),
        (None, PedagogicalEvalStatus.ERROR),
        (JudgeGate.APPROVED, PedagogicalEvalStatus.SKIPPED),
        (None, PedagogicalEvalStatus.PARTIAL),
    ],
)
def test_unusable_evaluations_are_left_out_of_the_report(
    session: Session, gate: JudgeGate | None, status: PedagogicalEvalStatus
) -> None:
    question = _question(
        session, evaluation=_evaluation(gate, status=status).model_dump(mode="json")
    )
    submit_review(session, question_id=question.id, decision=ReviewDecision.APPROVE)
    session.commit()

    assert build_calibration_pairs(session) == []
    assert build_calibration_report(session).n == 0


def test_a_question_with_no_review_is_not_a_pair(session: Session) -> None:
    _question(session, evaluation=_evaluation().model_dump(mode="json"))

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
        {"status": "completed", "metrics": "not a list"},
        {"status": "completed", "gate": "excellent"},
        {"status": "invented", "gate": "approved"},
        "not an object at all",
    ],
)
def test_a_stored_evaluation_that_no_longer_validates_is_skipped(
    session: Session, caplog: pytest.LogCaptureFixture, blob: object
) -> None:
    stale = _question(session, evaluation=blob)
    submit_review(session, question_id=stale.id, decision=ReviewDecision.APPROVE)
    usable = _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    session.commit()

    with caplog.at_level(logging.WARNING, logger="app.calibration.service"):
        pairs = build_calibration_pairs(session)

    assert [pair.question_id for pair in pairs] == [usable.id]
    assert f"Skipping question {stale.id}" in caplog.text


# -------------------------------------------------------------------- endpoint


def test_results_on_an_empty_database_report_nulls(client: TestClient) -> None:
    response = client.get("/api/calibration/results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["n"] == 0
    assert payload["judge_accept_count"] == 0
    assert payload["agreement"] is None
    assert payload["auto_accept_precision"] is None
    assert payload["unsafe_auto_accept_rate"] is None
    assert [row["n"] for row in payload["metrics"]] == [0, 0, 0]
    assert payload["subtopic_confusions"] == []
    assert payload["difficulty_confusions"] == []


def test_results_report_the_stored_agreement(client: TestClient, session: Session) -> None:
    _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    _judged(session, JudgeGate.APPROVED, ReviewDecision.REJECT)
    _judged(session, JudgeGate.NEEDS_REVIEW, ReviewDecision.REJECT)
    # Neither of these may reach the denominator.
    _question(
        session,
        evaluation=_evaluation(None, status=PedagogicalEvalStatus.SKIPPED).model_dump(mode="json"),
    )
    _question(session, evaluation=_evaluation().model_dump(mode="json"))

    payload = client.get("/api/calibration/results").json()

    assert payload["n"] == 3
    assert payload["judge_accept_count"] == 2
    assert payload["agreement"] == 0.6667
    assert payload["auto_accept_precision"] == 0.5
    assert payload["unsafe_auto_accept_rate"] == 0.5


def test_pairs_expose_the_evidence_behind_the_figures(client: TestClient, session: Session) -> None:
    agreeing = _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    disagreeing = _judged(session, JudgeGate.APPROVED, ReviewDecision.REJECT)
    excluded = _question(
        session,
        evaluation=_evaluation(None, status=PedagogicalEvalStatus.SKIPPED).model_dump(mode="json"),
    )

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
    _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)

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
        "metrics",
        "subtopic_confusions",
        "difficulty_confusions",
    }


# ------------------------------------------------------------------------ page


def test_the_feedback_page_states_an_honest_empty_calibration(client: TestClient) -> None:
    body = client.get("/feedback").text

    assert "Judge calibration" in body
    assert "No question has both a completed judge evaluation and a professor review yet" in body


def test_the_feedback_page_shows_the_figures_and_their_evidence(
    client: TestClient, session: Session
) -> None:
    agreeing = _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    disagreeing = _judged(session, JudgeGate.APPROVED, ReviewDecision.REJECT)

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
    _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)

    body = client.get("/feedback").text

    assert "small sample" in body
    assert str(MIN_INFORMATIVE_SAMPLE) in body


def test_a_null_rate_renders_as_a_dash_rather_than_zero(
    client: TestClient, session: Session
) -> None:
    """No judge accept means no precision to report -- not a precision of zero."""
    _judged(session, JudgeGate.NEEDS_REVIEW, ReviewDecision.REJECT)

    body = client.get("/feedback").text

    for label in ("Auto-accept precision", "Unsafe auto-accept rate"):
        cell = body.split(f"{label}</dt>", 1)[1].split("</dd>", 1)[0]
        assert "—" in cell, f"{label} must render as a dash"
        assert "%" not in cell, f"{label} must not invent a percentage"
    # The rate that does have a denominator is still reported.
    assert "100.0% of 1" in body
