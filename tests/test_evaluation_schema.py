"""Metric verdict scoring, the derived gate, and the stored evaluation shape."""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from app.domain.enums import Difficulty, JudgeGate, JudgeMetricId, RejectionReason
from app.evaluation.prompts import JUDGE_ISSUE_CODES, RUBRIC_VERSION
from app.evaluation.schema import (
    DifficultyVerdict,
    GeneratabilityVerdict,
    IssuesVerdict,
    MetricResult,
    MetricStatus,
    PedagogicalEvalStatus,
    SubtopicVerdict,
    derive_gate,
    evaluation_from_metrics,
    failed_metric,
    humanize_judge_error_detail,
    result_from_difficulty,
    result_from_generatability,
    result_from_issues,
    result_from_subtopic,
    skipped_evaluation,
)


def _passing(metric: JudgeMetricId, passed: bool) -> MetricResult:
    return MetricResult(metric=metric, passed=passed, rationale="because")


def test_rubric_version_locked() -> None:
    """A change here invalidates comparisons with every stored evaluation."""
    assert RUBRIC_VERSION == "question-metrics@1"


def test_all_four_metrics_are_judged() -> None:
    assert [metric.value for metric in JudgeMetricId] == [
        "issues",
        "subtopic",
        "difficulty",
        "generatability",
    ]


# ------------------------------------------------------------------ gate truth table


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ((True, True, True, True), JudgeGate.APPROVED),
        ((False, False, False, False), JudgeGate.REJECT),
        ((True, True, True, False), JudgeGate.NEEDS_REVIEW),
        ((False, False, False, True), JudgeGate.NEEDS_REVIEW),
        ((True, False, True, False), JudgeGate.NEEDS_REVIEW),
    ],
)
def test_gate_counts_passing_metrics(verdicts: tuple[bool, ...], expected: JudgeGate) -> None:
    metrics = [
        _passing(metric, passed) for metric, passed in zip(JudgeMetricId, verdicts, strict=True)
    ]
    assert derive_gate(metrics) is expected


def test_gate_covers_every_combination() -> None:
    """Only all-true approves and only all-false rejects; the rest need review."""
    for verdicts in itertools.product([True, False], repeat=len(JudgeMetricId)):
        metrics = [
            _passing(metric, passed) for metric, passed in zip(JudgeMetricId, verdicts, strict=True)
        ]
        gate = derive_gate(metrics)
        if all(verdicts):
            assert gate is JudgeGate.APPROVED
        elif not any(verdicts):
            assert gate is JudgeGate.REJECT
        else:
            assert gate is JudgeGate.NEEDS_REVIEW


def test_gate_is_absent_when_a_metric_is_missing() -> None:
    metrics = [_passing(metric, True) for metric in list(JudgeMetricId)[:3]]
    assert derive_gate(metrics) is None


def test_gate_is_absent_when_a_metric_failed() -> None:
    metrics = [_passing(metric, True) for metric in list(JudgeMetricId)[:3]]
    metrics.append(failed_metric(JudgeMetricId.GENERATABILITY, detail="down"))
    assert derive_gate(metrics) is None


# --------------------------------------------------------------------- pass derivation


def test_issues_metric_passes_only_with_no_issue_at_all() -> None:
    clean = result_from_issues(IssuesVerdict(rationale="sound"))
    coded = result_from_issues(
        IssuesVerdict(issue_codes=[RejectionReason.AMBIGUOUS], rationale="two readings")
    )
    custom = result_from_issues(IssuesVerdict(custom_issue="odd", rationale="odd"))

    assert clean.passed is True
    assert coded.passed is False
    assert custom.passed is False


def test_blank_custom_issue_is_not_an_issue() -> None:
    result = result_from_issues(IssuesVerdict(custom_issue="   ", rationale="sound"))
    assert result.passed is True
    assert result.custom_issue is None


def test_subtopic_metric_compares_as_a_set() -> None:
    verdict = SubtopicVerdict(topic_id=7, subtopic_ids=[2, 1], rationale="same")
    assert result_from_subtopic(verdict, claimed=[1, 2], topic_id=7).passed is True
    assert result_from_subtopic(verdict, claimed=[1], topic_id=7).passed is False
    assert result_from_subtopic(verdict, claimed=[1, 2], topic_id=8).passed is False


def test_difficulty_metric_records_what_the_judge_would_assign() -> None:
    verdict = DifficultyVerdict(difficulty=Difficulty.HARD, rationale="composed")
    result = result_from_difficulty(verdict, requested=Difficulty.EASY)
    assert result.passed is False
    assert result.proposed_difficulty is Difficulty.HARD


def test_generatability_metric_mirrors_the_verdict() -> None:
    yes = result_from_generatability(
        GeneratabilityVerdict(should_have_generated=True, rationale="enough")
    )
    no = result_from_generatability(
        GeneratabilityVerdict(should_have_generated=False, rationale="a heading only")
    )
    assert yes.passed is True
    assert no.passed is False


def test_a_verdict_needs_a_rationale() -> None:
    with pytest.raises(ValidationError):
        GeneratabilityVerdict(should_have_generated=True, rationale="")


def test_subtopic_verdict_needs_at_least_one_subtopic() -> None:
    with pytest.raises(ValidationError):
        SubtopicVerdict(topic_id=1, subtopic_ids=[], rationale="none")


# ------------------------------------------------------------------ assembled evaluation


def test_evaluation_is_completed_when_every_judge_answered() -> None:
    metrics = [_passing(metric, True) for metric in JudgeMetricId]
    evaluation = evaluation_from_metrics(metrics, question_id=1, judge_model="m")
    assert evaluation.status is PedagogicalEvalStatus.COMPLETED
    assert evaluation.gate is JudgeGate.APPROVED
    assert evaluation.rubric_version == RUBRIC_VERSION


def test_evaluation_is_partial_when_one_judge_failed() -> None:
    metrics = [_passing(metric, True) for metric in list(JudgeMetricId)[:3]]
    metrics.append(failed_metric(JudgeMetricId.GENERATABILITY, detail="unavailable"))

    evaluation = evaluation_from_metrics(metrics, question_id=1, judge_model="m")

    assert evaluation.status is PedagogicalEvalStatus.PARTIAL
    assert evaluation.gate is None
    assert evaluation.error_details == ["generatability: unavailable"]


def test_evaluation_is_error_when_no_judge_answered() -> None:
    metrics = [failed_metric(metric, detail="down") for metric in JudgeMetricId]
    evaluation = evaluation_from_metrics(metrics, question_id=1, judge_model="m")
    assert evaluation.status is PedagogicalEvalStatus.ERROR
    assert evaluation.gate is None


def test_skipped_evaluation_carries_no_gate() -> None:
    evaluation = skipped_evaluation(question_id=3)
    assert evaluation.status is PedagogicalEvalStatus.SKIPPED
    assert evaluation.gate is None
    assert evaluation.skip_reason == "deterministic_failed"
    assert evaluation.metrics == []


def test_failed_metric_is_absent_not_failing() -> None:
    result = failed_metric(JudgeMetricId.ISSUES, detail="503")
    assert result.status is MetricStatus.ERROR
    assert result.passed is None


def test_metric_lookup_returns_none_for_an_unanswered_metric() -> None:
    evaluation = evaluation_from_metrics(
        [_passing(JudgeMetricId.ISSUES, True)], question_id=1, judge_model="m"
    )
    assert evaluation.metric(JudgeMetricId.ISSUES) is not None
    assert evaluation.metric(JudgeMetricId.DIFFICULTY) is None


# ------------------------------------------------------------------------ vocabulary


def test_judge_issue_codes_exclude_what_other_judges_own() -> None:
    """Topic, difficulty and bank-wide duplication are not the issue judge's call."""
    assert RejectionReason.WRONG_TOPIC_SUBTOPIC not in JUDGE_ISSUE_CODES
    assert RejectionReason.TOO_EASY not in JUDGE_ISSUE_CODES
    assert RejectionReason.TOO_DIFFICULT not in JUDGE_ISSUE_CODES
    assert RejectionReason.TOO_SIMILAR_REPETITIVE not in JUDGE_ISSUE_CODES
    assert RejectionReason.OTHER not in JUDGE_ISSUE_CODES


def test_judge_issue_codes_are_professor_codes() -> None:
    """Both sides must name the same problem the same way, or nothing compares."""
    assert set(JUDGE_ISSUE_CODES) <= set(RejectionReason)


@pytest.mark.parametrize(
    ("detail", "expected_fragment"),
    [
        ("", "could not complete"),
        ("ValidationError: missing field", "incomplete"),
        ("malformed output", "malformed"),
        ("HTTP 503 from provider", "unavailable"),
        ("something specific", "something specific"),
    ],
)
def test_humanized_errors_stay_readable(detail: str, expected_fragment: str) -> None:
    assert expected_fragment in humanize_judge_error_detail(detail)
