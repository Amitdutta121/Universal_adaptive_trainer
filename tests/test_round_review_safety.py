"""A round cannot send an uncertified question to the professor queue."""

from types import SimpleNamespace

import pytest

from app.domain.enums import CustomJudgeKind, Difficulty, JudgeMetricId, QuestionType
from app.domain.questions import Question
from app.evaluation.custom import CustomJudgeResult, CustomRule
from app.evaluation.schema import (
    MetricResult,
    MetricStatus,
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
)
from app.generation.review import RoundReview
from app.generation.spec import QuestionSpec


def _review(metrics, rules=()):
    evaluation = PedagogicalEvaluation(status=PedagogicalEvalStatus.COMPLETED, metrics=metrics)
    judge = SimpleNamespace(evaluate=lambda question: evaluation)
    return RoundReview(
        judge,
        rules,
        spec=QuestionSpec(
            curriculum_version_id=1,
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.MEDIUM,
            source_section_ids=[1],
            target_subtopic_id=2,
        ),
    )


def _passing():
    return [
        MetricResult(
            metric=JudgeMetricId.DIFFICULTY, passed=True, proposed_difficulty=Difficulty.MEDIUM
        ),
        MetricResult(metric=JudgeMetricId.SUBTOPIC, passed=True, proposed_subtopic_ids=[2]),
    ]


@pytest.mark.parametrize("metric", [JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC])
@pytest.mark.parametrize("status", ["missing", "error", "failed"])
def test_a_required_judge_must_answer_and_pass(metric, status):
    metrics = _passing()
    if status == "missing":
        metrics = [entry for entry in metrics if entry.metric is not metric]
    else:
        for entry in metrics:
            if entry.metric is metric:
                entry.status = MetricStatus.ERROR if status == "error" else MetricStatus.COMPLETED
                entry.passed = None if status == "error" else False
    assert _review(metrics)(Question(prompt="Q", subtopic_ids=[2]))


@pytest.mark.parametrize("answer", [None, False, "missing"])
def test_custom_rules_must_answer_and_pass(monkeypatch, answer):
    rule = CustomRule(
        id=4, rule_text="No globals", kind=CustomJudgeKind.PATTERN, pattern="ast:Global"
    )
    results = (
        []
        if answer == "missing"
        else [
            CustomJudgeResult(judge_id=4, rule_text=rule.rule_text, kind=rule.kind, passed=answer)
        ]
    )
    monkeypatch.setattr(
        "app.generation.review.custom_judges.run_custom_judges", lambda *args, **kwargs: results
    )
    assert _review(_passing(), [rule])(Question(prompt="Q", subtopic_ids=[2]))


def test_confirmed_target_can_use_a_passing_legacy_verdict_without_proposed_ids():
    metrics = _passing()
    metrics[1].proposed_subtopic_ids = []
    assert not _review(metrics)(Question(prompt="Q", subtopic_ids=[2]))
