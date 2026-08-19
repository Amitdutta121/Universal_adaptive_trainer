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
    HELD_OUT_DIVISOR,
    PROFESSOR_OBJECTIONS,
    CalibrationLabel,
    CalibrationPair,
    QuadrantCell,
    build_calibration_pairs,
    build_calibration_report,
    build_type_calibrations,
    for_repair,
    held_out,
    is_held_out,
    judge_label,
    metrics_from_pairs,
    professor_label,
    quadrant_cell,
    reports_by_type,
)
from app.domain.enums import (
    JudgeGate,
    JudgeMetricId,
    QuestionStatus,
    QuestionType,
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


def _question(
    session: Session,
    *,
    evaluation: object | None,
    question_type: QuestionType | None = None,
) -> QuestionRow:
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
            question_type=question_type,
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
    question_type: QuestionType | None = None,
) -> QuestionRow:
    """A question with one stored evaluation and one professor review."""
    question = _question(
        session,
        evaluation=_evaluation(gate, failing=failing).model_dump(mode="json"),
        question_type=question_type,
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


# -------------------------------------------------------------------- quadrant


@pytest.mark.parametrize(
    ("judge", "professor", "expected"),
    [
        (ACCEPT, ACCEPT, QuadrantCell.CONFIRMED_GOOD),
        (ACCEPT, NEEDS_REVIEW, QuadrantCell.MISSED),
        (NEEDS_REVIEW, ACCEPT, QuadrantCell.FALSE_ALARM),
        (NEEDS_REVIEW, NEEDS_REVIEW, QuadrantCell.CONFIRMED_BAD),
    ],
)
def test_every_label_combination_maps_to_its_cell(
    judge: CalibrationLabel, professor: CalibrationLabel, expected: QuadrantCell
) -> None:
    assert quadrant_cell(judge, professor) is expected
    assert _pairs((judge, professor))[0].cell is expected


def test_the_quadrant_counts_every_pair_exactly_once() -> None:
    report = metrics_from_pairs(
        _pairs(
            (ACCEPT, ACCEPT),
            (ACCEPT, ACCEPT),
            (ACCEPT, NEEDS_REVIEW),
            (NEEDS_REVIEW, ACCEPT),
            (NEEDS_REVIEW, NEEDS_REVIEW),
        )
    )
    quadrant = report.quadrant

    assert (quadrant.confirmed_good, quadrant.missed) == (2, 1)
    assert (quadrant.false_alarm, quadrant.confirmed_bad) == (1, 1)
    counted = quadrant.confirmed_good + quadrant.missed
    assert counted + quadrant.false_alarm + quadrant.confirmed_bad == report.n


def test_only_the_two_judge_accept_cells_feed_auto_accept_precision() -> None:
    """The cells where the judge did not accept must not move the safety figure.

    This is the whole reason the quadrant is published beside the rate: a
    professor cannot see from ``auto_accept_precision`` alone that half their
    measured questions were never in its denominator.
    """
    accepted_only = metrics_from_pairs(_pairs((ACCEPT, ACCEPT), (ACCEPT, NEEDS_REVIEW)))
    plus_rejected = metrics_from_pairs(
        _pairs(
            (ACCEPT, ACCEPT),
            (ACCEPT, NEEDS_REVIEW),
            (NEEDS_REVIEW, ACCEPT),
            (NEEDS_REVIEW, NEEDS_REVIEW),
        )
    )

    assert accepted_only.auto_accept_precision == plus_rejected.auto_accept_precision == 0.5
    assert accepted_only.judge_accept_count == plus_rejected.judge_accept_count == 2
    assert plus_rejected.n == 4


def test_a_missed_pair_names_the_reviewer_that_passed_it(session: Session) -> None:
    """A rejection for TOO_EASY contradicts the difficulty reviewer, and no other."""
    _judged(session, JudgeGate.APPROVED, ReviewDecision.REJECT)

    pair = build_calibration_pairs(session)[0]

    assert pair.cell is QuadrantCell.MISSED
    assert pair.missed_metrics == [JudgeMetricId.DIFFICULTY]
    assert pair.false_alarm_metrics == []


def test_a_false_alarm_names_the_reviewer_that_flagged_it(session: Session) -> None:
    _judged(
        session,
        JudgeGate.NEEDS_REVIEW,
        ReviewDecision.APPROVE,
        failing={JudgeMetricId.DIFFICULTY},
    )

    pair = build_calibration_pairs(session)[0]

    assert pair.cell is QuadrantCell.FALSE_ALARM
    assert pair.false_alarm_metrics == [JudgeMetricId.DIFFICULTY]
    assert pair.missed_metrics == []


def test_generatability_is_never_blamed_for_anything(session: Session) -> None:
    """The professor has no reason that contradicts it, so it has no verdict to lose.

    Attributing a miss to the nearest judge would send the professor to repair a
    prompt that was not at fault.
    """
    assert JudgeMetricId.GENERATABILITY not in PROFESSOR_OBJECTIONS
    _judged(session, JudgeGate.APPROVED, ReviewDecision.REJECT)
    _judged(
        session,
        JudgeGate.NEEDS_REVIEW,
        ReviewDecision.APPROVE,
        failing={JudgeMetricId.GENERATABILITY},
    )

    for pair in build_calibration_pairs(session):
        assert JudgeMetricId.GENERATABILITY not in pair.missed_metrics
        assert JudgeMetricId.GENERATABILITY not in pair.false_alarm_metrics


def test_an_unattributable_miss_reports_no_reviewer_rather_than_a_wrong_one(
    session: Session,
) -> None:
    """A rejection reason outside every metric's vocabulary blames nobody."""
    question = _question(
        session, evaluation=_evaluation(JudgeGate.APPROVED).model_dump(mode="json")
    )
    submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_SIMILAR_REPETITIVE],
    )
    session.commit()

    pair = build_calibration_pairs(session)[0]

    assert pair.cell is QuadrantCell.MISSED
    assert pair.missed_metrics == []


def test_pairs_are_grouped_by_question_type(session: Session) -> None:
    mcq = _judged(
        session,
        JudgeGate.APPROVED,
        ReviewDecision.APPROVE,
        question_type=QuestionType.MULTIPLE_CHOICE,
    )
    debugging = _judged(
        session,
        JudgeGate.APPROVED,
        ReviewDecision.REJECT,
        question_type=QuestionType.DEBUGGING,
    )

    slices = build_type_calibrations(session)

    assert [slice_.question_type for slice_ in slices] == [
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.DEBUGGING,
    ]
    assert [pair.question_id for pair in slices[0].pairs] == [mcq.id]
    assert slices[0].report.auto_accept_precision == 1.0
    assert [pair.question_id for pair in slices[1].pairs] == [debugging.id]
    assert slices[1].report.auto_accept_precision == 0.0


def test_a_type_nobody_reviewed_is_absent_rather_than_a_row_of_zeroes(session: Session) -> None:
    _judged(
        session,
        JudgeGate.APPROVED,
        ReviewDecision.APPROVE,
        question_type=QuestionType.MULTIPLE_CHOICE,
    )

    slices = build_type_calibrations(session)

    assert len(slices) == 1
    assert QuestionType.CODING not in [slice_.question_type for slice_ in slices]


def test_a_question_with_no_type_groups_under_none_and_comes_last(session: Session) -> None:
    """A question generated before the field existed declared no type to fold in."""
    _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    _judged(
        session,
        JudgeGate.APPROVED,
        ReviewDecision.APPROVE,
        question_type=QuestionType.PARSONS,
    )

    slices = build_type_calibrations(session)

    assert [slice_.question_type for slice_ in slices] == [QuestionType.PARSONS, None]


def test_the_type_slices_partition_the_pairs(session: Session) -> None:
    """Every measured question appears in exactly one slice."""
    for question_type in (QuestionType.CODING, QuestionType.TRUE_FALSE, None):
        _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE, question_type=question_type)
    pairs = build_calibration_pairs(session)

    slices = reports_by_type(pairs)

    assert sum(slice_.report.n for slice_ in slices) == len(pairs) == 3
    seen = [pair.question_id for slice_ in slices for pair in slice_.pairs]
    assert sorted(seen) == sorted(pair.question_id for pair in pairs)


def test_in_cell_selects_only_that_cell(session: Session) -> None:
    good = _judged(
        session, JudgeGate.APPROVED, ReviewDecision.APPROVE, question_type=QuestionType.CODING
    )
    missed = _judged(
        session, JudgeGate.APPROVED, ReviewDecision.REJECT, question_type=QuestionType.CODING
    )

    slice_ = build_type_calibrations(session)[0]

    assert [pair.question_id for pair in slice_.in_cell(QuadrantCell.CONFIRMED_GOOD)] == [good.id]
    assert [pair.question_id for pair in slice_.in_cell(QuadrantCell.MISSED)] == [missed.id]
    assert slice_.in_cell(QuadrantCell.FALSE_ALARM) == []


# ---------------------------------------------------------- held-out check set


def test_the_split_is_keyed_on_the_question_id_and_never_moves() -> None:
    """A question must be in the same half before and after any repair."""
    assert HELD_OUT_DIVISOR == 3
    assert [is_held_out(question_id) for question_id in (1, 2, 3, 4, 5, 6)] == [
        False,
        False,
        True,
        False,
        False,
        True,
    ]
    assert all(is_held_out(9) for _ in range(5))


def test_repair_lists_exclude_the_held_out_pairs(session: Session) -> None:
    for _ in range(6):
        _judged(
            session,
            JudgeGate.APPROVED,
            ReviewDecision.REJECT,
            question_type=QuestionType.CODING,
        )

    slice_ = build_type_calibrations(session)[0]
    repairable = slice_.to_repair(QuadrantCell.MISSED)

    assert [pair.question_id for pair in slice_.in_cell(QuadrantCell.MISSED)] == [1, 2, 3, 4, 5, 6]
    assert [pair.question_id for pair in repairable] == [1, 2, 4, 5]
    assert all(not pair.held_out for pair in repairable)


def test_the_check_report_scores_the_held_out_pairs_only(session: Session) -> None:
    """Ids 1 and 2 are repairable; id 3 is the only one that scores the repair."""
    for decision in (ReviewDecision.REJECT, ReviewDecision.REJECT, ReviewDecision.APPROVE):
        _judged(session, JudgeGate.APPROVED, decision, question_type=QuestionType.CODING)

    slice_ = build_type_calibrations(session)[0]

    # Over everything the judge looks poor: one approval in three.
    assert slice_.report.n == 3
    assert slice_.report.auto_accept_precision == 0.3333
    # The held-out third is question 3 alone, which the professor approved.
    assert slice_.check_report.n == 1
    assert slice_.check_report.auto_accept_precision == 1.0


def test_the_two_halves_partition_the_pairs(session: Session) -> None:
    for _ in range(7):
        _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    pairs = build_calibration_pairs(session)

    reserved = held_out(pairs)
    repairable = for_repair(pairs)

    assert len(reserved) + len(repairable) == len(pairs) == 7
    assert not {pair.question_id for pair in reserved} & {pair.question_id for pair in repairable}


def test_the_split_does_not_change_the_overall_report(session: Session) -> None:
    """The figure the professor already reads must not be silently narrowed."""
    for _ in range(6):
        _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)

    slice_ = build_type_calibrations(session)[0]

    assert slice_.report.n == 6
    assert slice_.report.n == build_calibration_report(session).n


# -------------------------------------------------------- judge rubric versions


def test_a_report_names_every_judge_version_behind_it(session: Session) -> None:
    _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    stale = _evaluation(JudgeGate.APPROVED)
    stale.rubric_version = "ancient-1"
    question = _question(session, evaluation=stale.model_dump(mode="json"))
    submit_review(session, question_id=question.id, decision=ReviewDecision.APPROVE)
    session.commit()

    report = build_calibration_report(session)

    assert len(report.rubric_versions) == 2
    assert "ancient-1" in report.rubric_versions
    assert report.rubric_versions == sorted(report.rubric_versions)


def test_filtering_by_rubric_version_measures_one_judge_only(session: Session) -> None:
    current = _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)
    stale = _evaluation(JudgeGate.APPROVED)
    stale.rubric_version = "ancient-1"
    old = _question(session, evaluation=stale.model_dump(mode="json"))
    submit_review(
        session,
        question_id=old.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
    )
    session.commit()

    assert len(build_calibration_pairs(session)) == 2
    filtered = build_calibration_pairs(session, rubric_version="ancient-1")
    assert [pair.question_id for pair in filtered] == [old.id]
    assert current.id not in [pair.question_id for pair in filtered]


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
    assert [
        {key: pair[key] for key in ("question_id", "judge", "professor", "agrees", "cell")}
        for pair in payload["pairs"]
    ] == [
        {
            "question_id": agreeing.id,
            "judge": "accept",
            "professor": "accept",
            "agrees": True,
            "cell": "confirmed_good",
        },
        {
            "question_id": disagreeing.id,
            "judge": "accept",
            "professor": "needs_review",
            "agrees": False,
            "cell": "missed",
        },
    ]
    assert excluded.id not in [pair["question_id"] for pair in payload["pairs"]]


def test_pairs_on_an_empty_database_are_empty(client: TestClient) -> None:
    assert client.get("/api/calibration/pairs").json() == {"pairs": [], "total": 0}


def test_the_quadrant_endpoint_reports_per_type_cells(client: TestClient, session: Session) -> None:
    _judged(
        session,
        JudgeGate.APPROVED,
        ReviewDecision.APPROVE,
        question_type=QuestionType.MULTIPLE_CHOICE,
    )
    missed = _judged(
        session,
        JudgeGate.APPROVED,
        ReviewDecision.REJECT,
        question_type=QuestionType.MULTIPLE_CHOICE,
    )

    payload = client.get("/api/calibration/quadrant").json()

    assert payload["overall"]["quadrant"] == {
        "confirmed_good": 1,
        "missed": 1,
        "false_alarm": 0,
        "confirmed_bad": 0,
    }
    assert len(payload["types"]) == 1
    slice_ = payload["types"][0]
    assert slice_["question_type"] == "multiple_choice"
    assert slice_["report"]["auto_accept_precision"] == 0.5
    flagged = [pair for pair in slice_["pairs"] if pair["cell"] == "missed"]
    assert [pair["question_id"] for pair in flagged] == [missed.id]
    assert flagged[0]["missed_metrics"] == ["difficulty"]


def test_the_quadrant_endpoint_states_which_reviewer_cannot_be_blamed(
    client: TestClient,
) -> None:
    payload = client.get("/api/calibration/quadrant").json()

    assert payload["unattributable_metrics"] == ["generatability"]
    assert payload["overall"]["n"] == 0
    assert payload["types"] == []


def test_the_quadrant_endpoint_publishes_the_split_rule(
    client: TestClient, session: Session
) -> None:
    for _ in range(3):
        _judged(
            session,
            JudgeGate.APPROVED,
            ReviewDecision.APPROVE,
            question_type=QuestionType.CODING,
        )

    payload = client.get("/api/calibration/quadrant").json()
    slice_ = payload["types"][0]

    assert payload["held_out_divisor"] == HELD_OUT_DIVISOR
    assert slice_["report"]["n"] == 3
    assert slice_["check_report"]["n"] == 1
    assert [pair["question_id"] for pair in slice_["pairs"] if pair["held_out"]] == [3]


def test_the_quadrant_endpoint_filters_by_rubric_version(
    client: TestClient, session: Session
) -> None:
    _judged(session, JudgeGate.APPROVED, ReviewDecision.APPROVE)

    matched = client.get("/api/calibration/quadrant", params={"rubric_version": "ancient-1"}).json()
    unmatched = client.get("/api/calibration/quadrant").json()

    assert matched["overall"]["n"] == 0
    assert unmatched["overall"]["n"] == 1


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
    assert "/api/calibration/quadrant" in schema["paths"]
    for path in ("/api/calibration/results", "/api/calibration/pairs", "/api/calibration/quadrant"):
        assert set(schema["paths"][path]) == {"get"}, f"{path} must stay read-only"
    properties = schema["components"]["schemas"]["CalibrationResultsResponse"]["properties"]
    assert set(properties) == {
        "n",
        "judge_accept_count",
        "agreement",
        "auto_accept_precision",
        "unsafe_auto_accept_rate",
        "quadrant",
        "rubric_versions",
        "metrics",
        "subtopic_confusions",
        "difficulty_confusions",
    }
    quadrant = schema["components"]["schemas"]["CalibrationQuadrantResponse"]["properties"]
    assert set(quadrant) == {
        "overall",
        "types",
        "unattributable_metrics",
        "held_out_divisor",
    }
