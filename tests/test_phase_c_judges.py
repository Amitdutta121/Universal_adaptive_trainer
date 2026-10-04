"""Custom rules, observed review evidence and course isolation."""

import pytest
from llm_fakes import metric_results

from app.calibration import build_calibration_report
from app.domain.enums import (
    CustomJudgeKind,
    Difficulty,
    EvaluationTrigger,
    JudgeMetricId,
    ReviewDecision,
)
from app.domain.questions import Question
from app.errors import DomainRuleError, LLMRequestError
from app.evaluation.batch_service import record_evaluation
from app.evaluation.custom import CustomRule, RuleVerdict, load_rules, run_custom_judges
from app.evaluation.schema import evaluation_from_metrics, failed_metric
from app.feedback import route_review_outcome, submit_review
from app.persistence.models import (
    CourseRow,
    CurriculumVersionRow,
    QuestionRow,
    SubtopicRow,
    TopicRow,
)


def taxonomy(session, name):
    course = CourseRow(name=name)
    session.add(course)
    session.flush()
    version = CurriculumVersionRow(label=name, course_id=course.id)
    session.add(version)
    session.flush()
    topic = TopicRow(name="Loops", curriculum_version_id=version.id)
    session.add(topic)
    session.flush()
    subs = [SubtopicRow(name=n, topic_id=topic.id) for n in ("For", "While")]
    session.add_all(subs)
    session.commit()
    return course, version, topic, subs


def evaluated_question(session, version, topic, subs, *, proposed=True):
    metrics = [
        m
        for m in metric_results()
        if m.metric in (JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC)
    ]
    for metric in metrics:
        if metric.metric is JudgeMetricId.DIFFICULTY:
            metric.proposed_difficulty = Difficulty.EASY if proposed else None
        else:
            metric.proposed_subtopic_ids = [subs[0].id] if proposed else []
    evaluation = evaluation_from_metrics(
        metrics, question_id=None, judge_model="fake", expected=[m.metric for m in metrics]
    )
    question = QuestionRow(
        prompt="Loop",
        difficulty=Difficulty.EASY,
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[subs[0].id],
        pedagogical_eval=evaluation.model_dump(mode="json"),
    )
    session.add(question)
    session.commit()
    return question, evaluation


@pytest.mark.parametrize("proposed", [True, False])
def test_accepted_corrections_update_selection_but_keep_judge_evidence(session, proposed):
    _, version, topic, subs = taxonomy(session, "A")
    question, _ = evaluated_question(session, version, topic, subs, proposed=proposed)
    original = question.pedagogical_eval.copy()
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.APPROVE,
        corrected_difficulty=Difficulty.HARD,
        corrected_subtopic_ids=[subs[1].id, subs[1].id],
    )
    outcome = route_review_outcome(session, review)
    session.commit()
    session.expire_all()
    assert question.difficulty is Difficulty.HARD
    assert list(question.subtopic_ids) == [subs[1].id]
    assert question.pedagogical_eval == original
    assert set(outcome.attributed_metrics) == {JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC}
    assert outcome.calls_for_judge_repair
    report = build_calibration_report(session)
    for metric in report.metrics:
        if metric.metric in (JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC):
            assert metric.n == 1 and metric.agreement == 0


def test_confirmations_override_reasons_and_rejection_does_not_reclassify(session):
    _, version, topic, subs = taxonomy(session, "A")
    question, _ = evaluated_question(session, version, topic, subs)
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.REJECT,
        corrected_difficulty=Difficulty.EASY,
        corrected_subtopic_ids=[subs[0].id],
    )
    outcome = route_review_outcome(session, review)
    assert outcome.attributed_metrics == []
    assert question.difficulty is Difficulty.EASY
    assert list(question.subtopic_ids) == [subs[0].id]
    report = build_calibration_report(session)
    assert all(m.agreement == 1 for m in report.metrics if m.n)


def test_absent_confirmation_and_foreign_subtopics(session):
    _, version, topic, subs = taxonomy(session, "A")
    _, _, _, foreign = taxonomy(session, "B")
    question, _ = evaluated_question(session, version, topic, subs)
    with pytest.raises(DomainRuleError):
        submit_review(
            session,
            question_id=question.id,
            decision=ReviewDecision.APPROVE,
            corrected_subtopic_ids=[foreign[0].id],
        )
    review = submit_review(session, question_id=question.id, decision=ReviewDecision.REJECT)
    session.commit()
    session.refresh(review)
    assert review.corrected_subtopic_ids is None
    assert review.corrected_difficulty is None


@pytest.mark.parametrize(
    "pattern,code,passed",
    [
        (r"\bglobal\b", "global x", False),
        ("ast:Global,Nonlocal", "global x", False),
        ("ast:Global", "print('global')", True),
        ("ast:While", "while True: break", False),
    ],
)
def test_pattern_runner(pattern, code, passed):
    question = Question(prompt="What happens?", content={"code": code})
    rule = CustomRule(
        id=1, rule_text="Avoid forbidden syntax", kind=CustomJudgeKind.PATTERN, pattern=pattern
    )
    result = run_custom_judges(question, [rule])[0]
    assert result.passed is passed
    assert bool(result.reason) is (not passed)


def test_llm_runner_and_unanswered_errors():
    class Client:
        description = "fake"

        def complete_structured(self, **kwargs):
            assert "No loops" in kwargs["prompt"]
            return RuleVerdict(passes=False, reason="Remove the loop.")

    rule = CustomRule(id=1, rule_text="No loops", kind=CustomJudgeKind.LLM)
    result = run_custom_judges(Question(prompt="Loop"), [rule], client=Client())[0]
    assert result.passed is False and result.reason == "Remove the loop."

    class Broken(Client):
        def complete_structured(self, **kwargs):
            raise LLMRequestError("offline")

    assert run_custom_judges(Question(prompt="Loop"), [rule], client=Broken())[0].passed is None


def test_custom_crud_validation_course_scope_and_current_history(client, session):
    course, version, topic, subs = taxonomy(session, "A")
    other, foreign, _, _ = taxonomy(session, "B")
    headers = {"X-Course-Id": str(course.id)}
    payload = {
        "curriculum_version_id": version.id,
        "rule_text": "No global",
        "kind": "pattern",
        "pattern": "ast:Global",
    }
    created = client.post("/api/custom-judges", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    judge_id = created.json()["id"]
    assert len(load_rules(session, version.id)) == 1
    assert load_rules(session, foreign.id) == []
    assert (
        client.get(
            "/api/custom-judges", params={"curriculum_version_id": foreign.id}, headers=headers
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/custom-judges/{judge_id}",
            json={"enabled": False},
            headers={"X-Course-Id": str(other.id)},
        ).status_code
        == 404
    )
    for invalid in (
        {"pattern": "ast:NotARealNode"},
        {"pattern": "["},
        {"rule_text": "   "},
        {"enabled": None},
        {"kind": None},
        {"pattern": None},
    ):
        assert (
            client.patch(
                f"/api/custom-judges/{judge_id}", json=invalid, headers=headers
            ).status_code
            == 422
        )
    updated = client.patch(
        f"/api/custom-judges/{judge_id}", json={"enabled": False}, headers=headers
    )
    assert updated.status_code == 200
    assert load_rules(session, version.id) == []
    assert (
        len(
            client.get(
                "/api/custom-judges", params={"curriculum_version_id": version.id}, headers=headers
            ).json()["judges"]
        )
        == 1
    )
    question, evaluation = evaluated_question(session, version, topic, subs)
    custom = run_custom_judges(
        Question(prompt="global x"),
        [
            CustomRule(
                id=judge_id,
                rule_text="No global",
                kind=CustomJudgeKind.PATTERN,
                pattern="ast:Global",
            )
        ],
    )
    record_evaluation(
        session,
        question.id,
        evaluation,
        run_id="good",
        trigger=EvaluationTrigger.GENERATION,
        custom_results=custom,
    )
    error = evaluation_from_metrics(
        [failed_metric(JudgeMetricId.DIFFICULTY, detail="offline")],
        question_id=question.id,
        judge_model="fake",
        expected=[JudgeMetricId.DIFFICULTY],
    )
    record_evaluation(
        session, question.id, error, run_id="error", trigger=EvaluationTrigger.BATCH_RERUN
    )
    session.commit()
    detail = client.get(f"/api/questions/{question.id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["custom_results"][0]["passed"] is False
    assert detail.json()["judge_trust"] is None
    question.style_id = "loop-test"
    session.commit()
    styled = client.get(f"/api/questions/{question.id}", headers=headers)
    assert styled.status_code == 200, styled.text
    assert styled.json()["judge_trust"] is not None
    assert (
        client.get(
            f"/api/questions/{question.id}", headers={"X-Course-Id": str(other.id)}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/questions/{question.id}/review",
            json={"decision": "reject"},
            headers={"X-Course-Id": str(other.id)},
        ).status_code
        == 404
    )
    rejected = client.post(
        f"/api/questions/{question.id}/review",
        json={"decision": "reject", "comment": "Optional note"},
        headers=headers,
    )
    assert rejected.status_code == 201, rejected.text
    assert rejected.json()["corrected_subtopic_ids"] is None


def test_partial_confirmation_does_not_measure_unconfirmed_metric(session):
    _, version, topic, subs = taxonomy(session, "A")
    question, _ = evaluated_question(session, version, topic, subs)
    submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.APPROVE,
        corrected_difficulty=Difficulty.EASY,
    )
    session.commit()
    report = build_calibration_report(session)
    counts = {metric.metric: metric.n for metric in report.metrics}
    assert counts[JudgeMetricId.DIFFICULTY] == 1
    assert counts[JudgeMetricId.SUBTOPIC] == 0


def test_corrected_join_rows_drive_coverage_and_student_candidates(session):
    from app.persistence.models import QuestionSetMemberRow, QuestionSetVersionRow
    from app.persistence.repositories import QuestionSetRepository

    _, version, topic, subs = taxonomy(session, "A")
    question, _ = evaluated_question(session, version, topic, subs)
    question.subtopic_ids.append(subs[1].id)
    frozen = QuestionSetVersionRow(label="Set", curriculum_version_id=version.id, question_count=1)
    session.add(frozen)
    session.flush()
    session.add(QuestionSetMemberRow(set_version_id=frozen.id, question_id=question.id))
    session.commit()
    submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.APPROVE,
        corrected_difficulty=Difficulty.HARD,
        corrected_subtopic_ids=[subs[1].id],
    )
    session.commit()
    repository = QuestionSetRepository(session)
    assert repository.coverage_counts() == {(subs[1].id, Difficulty.HARD): 1}
    assert (
        repository.candidates_for_cell(
            frozen.id, subtopic_id=subs[0].id, difficulty=Difficulty.EASY
        )
        == []
    )
    assert (
        repository.candidates_for_cell(
            frozen.id, subtopic_id=subs[1].id, difficulty=Difficulty.HARD
        )[0][0]
        == question.id
    )


def test_review_lists_and_stats_respect_course(client, session):
    course, version, topic, subs = taxonomy(session, "A")
    other, _, _, _ = taxonomy(session, "B")
    question, _ = evaluated_question(session, version, topic, subs)
    submit_review(session, question_id=question.id, decision=ReviewDecision.REJECT)
    session.commit()
    assert client.get("/api/reviews", headers={"X-Course-Id": str(course.id)}).json()["total"] == 1
    assert client.get("/api/reviews", headers={"X-Course-Id": str(other.id)}).json()["total"] == 0
    assert (
        client.get("/api/reviews/stats", headers={"X-Course-Id": str(other.id)}).json()["reviewed"]
        == 0
    )
