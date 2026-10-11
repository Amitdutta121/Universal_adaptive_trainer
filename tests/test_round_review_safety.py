"""A round cannot send an uncertified question to the professor queue."""

from types import SimpleNamespace

import pytest

from app.domain.enums import (
    CustomJudgeKind,
    Difficulty,
    JudgeMetricId,
    QuestionType,
    RejectionReason,
)
from app.domain.questions import GenerationAttempt, Question
from app.evaluation.custom import CustomJudgeResult, CustomRule
from app.evaluation.schema import (
    MetricResult,
    MetricStatus,
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
)
from app.generation.review import DUPLICATE_CHECK, RoundReview
from app.generation.spec import QuestionSpec
from app.retrieval.duplicates import SimilarQuestion


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
                if status == "failed" and metric is JudgeMetricId.SUBTOPIC:
                    entry.proposed_subtopic_ids = [99]
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


# ------------------------------------------------------------------ duplicates (ADR-063 point 6)


def _similar(score, *, exact=False):
    return SimilarQuestion(
        question_id=7, text="Old question text", score=score, exact=exact, model="fake-embed"
    )


def _dup_review(matches, judged):
    def evaluate(question):
        judged.append(question)
        return PedagogicalEvaluation(status=PedagogicalEvalStatus.COMPLETED, metrics=_passing())

    return RoundReview(
        SimpleNamespace(evaluate=evaluate),
        (),
        spec=QuestionSpec(
            curriculum_version_id=1,
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.MEDIUM,
            source_section_ids=[1],
            target_subtopic_id=2,
        ),
        duplicates=lambda question: matches,
        max_attempts=3,
    )


def _attempt(number):
    return Question(
        prompt="Q",
        subtopic_ids=[2],
        generation_attempts=[GenerationAttempt(number=number, accepted=True)],
    )


@pytest.mark.parametrize("match", [_similar(0.93), _similar(1.0, exact=True)])
def test_a_duplicate_fails_the_attempt_quoting_it_before_any_judge(match):
    judged = []
    review = _dup_review([match], judged)

    (failed,) = review(_attempt(1))

    assert failed.name == DUPLICATE_CHECK
    assert failed.detail == "it is too similar to: Old question text"
    assert judged == []


def test_a_similar_question_below_the_duplicate_line_passes_and_is_remembered():
    judged = []
    review = _dup_review([_similar(0.80)], judged)

    assert review(_attempt(1)) == []
    assert len(judged) == 1
    assert [match.score for match in review.last_similar] == [0.80]


def test_on_the_last_attempt_a_duplicate_is_judged_and_kept():
    judged = []
    review = _dup_review([_similar(0.95)], judged)

    assert review(_attempt(3)) == []
    assert len(judged) == 1 and review.last_evaluation is not None
    assert [match.score for match in review.last_similar] == [0.95]


def test_difficulty_off_by_one_band_is_kept_with_a_note():
    metrics = _passing()
    metrics[0].passed = False
    metrics[0].proposed_difficulty = Difficulty.HARD
    review = _review(metrics)
    assert review(Question(prompt="Q", subtopic_ids=[2])) == []
    assert review.last_notes == ["difficulty judge thinks this may be hard"]


def test_difficulty_off_by_two_bands_is_retried():
    review = RoundReview(
        SimpleNamespace(
            evaluate=lambda question: PedagogicalEvaluation(
                status=PedagogicalEvalStatus.COMPLETED,
                metrics=[
                    MetricResult(
                        metric=JudgeMetricId.DIFFICULTY,
                        passed=False,
                        proposed_difficulty=Difficulty.HARD,
                    ),
                    MetricResult(
                        metric=JudgeMetricId.SUBTOPIC, passed=True, proposed_subtopic_ids=[2]
                    ),
                ],
            )
        ),
        (),
        spec=QuestionSpec(
            curriculum_version_id=1,
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            source_section_ids=[1],
            target_subtopic_id=2,
        ),
    )
    failed = review(Question(prompt="Q", subtopic_ids=[2]))
    assert [check.name for check in failed] == ["difficulty_judge"]
    assert review.last_notes == []


def test_subtopic_overlap_is_kept_with_a_note():
    metrics = _passing()
    metrics[1].passed = False
    metrics[1].proposed_subtopic_ids = [2, 9]
    review = _review(metrics)
    assert review(Question(prompt="Q", subtopic_ids=[2])) == []
    assert review.last_notes == ["topic judge thinks this may still cover the target subtopic"]


def test_subtopic_with_no_overlap_is_retried():
    metrics = _passing()
    metrics[1].passed = False
    metrics[1].proposed_subtopic_ids = [9]
    failed = _review(metrics)(Question(prompt="Q", subtopic_ids=[2]))
    assert [check.name for check in failed] == ["topic_judge"]


def test_advisory_issue_codes_are_kept_with_a_note():
    metrics = _passing()
    metrics.append(
        MetricResult(
            metric=JudgeMetricId.ISSUES,
            passed=False,
            issue_codes=[RejectionReason.POOR_WORDING],
            rationale="wording",
        )
    )
    review = _review(metrics)
    assert review(Question(prompt="Q", subtopic_ids=[2])) == []
    assert review.last_notes == ["issues judge flagged wording, distractors or usefulness"]


def test_blocking_issue_codes_are_retried():
    metrics = _passing()
    metrics.append(
        MetricResult(
            metric=JudgeMetricId.ISSUES,
            passed=False,
            issue_codes=[RejectionReason.INCORRECT_ANSWER],
            rationale="wrong key",
        )
    )
    failed = _review(metrics)(Question(prompt="Q", subtopic_ids=[2]))
    assert [check.name for check in failed] == ["issues_judge"]
