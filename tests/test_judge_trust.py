"""Trust is scoped professor evidence; routing and audit counters are durable."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import CustomJudgeKind, Difficulty, QuestionStatus, ReviewDecision
from app.evaluation.trust import judge_trust, route_generated_question
from app.persistence.database import _alembic_config, init_db, verify_schema
from app.persistence.models import (
    CourseRow,
    CurriculumVersionRow,
    CustomJudgeRow,
    JudgeTrustCounterRow,
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    SubtopicRow,
    TopicRow,
)
from tests.conftest import TEST_PROFESSOR_ID


@pytest.fixture
def taxonomy(session):
    course = CourseRow(name="Trust course", owner_id=TEST_PROFESSOR_ID)
    session.add(course)
    session.flush()
    version = CurriculumVersionRow(label="v1", course_id=course.id)
    version.topics.append(TopicRow(name="Loops", subtopics=[SubtopicRow(name="for")]))
    session.add(version)
    session.flush()
    return version


def question(session, taxonomy, *, style="py.trace_output", model="judge-v1", rubric="r1"):
    topic = taxonomy.topics[0]
    row = QuestionRow(
        curriculum_version_id=taxonomy.id,
        topic_id=topic.id,
        difficulty=Difficulty.EASY,
        style_id=style,
        prompt="Question",
        status=QuestionStatus.VALIDATION_PASSED,
    )
    row.subtopic_ids = [topic.subtopics[0].id]
    row.pedagogical_eval = {
        "status": "completed",
        "judge_model": model,
        "rubric_version": rubric,
        "metrics": [
            {
                "metric": "difficulty",
                "status": "completed",
                "passed": True,
                "proposed_difficulty": "easy",
            },
            {
                "metric": "subtopic",
                "status": "completed",
                "passed": True,
                "proposed_topic_id": topic.id,
                "proposed_subtopic_ids": list(row.subtopic_ids),
            },
        ],
    }
    session.add(row)
    session.flush()
    return row


def review(session, row, *, agrees=True, explicit=True, decision=ReviewDecision.APPROVE):
    row_review = ProfessorReviewRow(
        question_id=row.id,
        decision=decision,
        corrected_difficulty=(Difficulty.EASY if agrees else Difficulty.HARD) if explicit else None,
        corrected_subtopic_ids=list(row.subtopic_ids) if explicit else [],
    )
    session.add(row_review)
    session.flush()
    return row_review


def seed(session, taxonomy, n=20, disagreements=0, custom=None, explicit=True):
    for index in range(n):
        row = question(session, taxonomy)
        route_generated_question(session, row, custom)
        review(session, row, agrees=index >= disagreements, explicit=explicit)


@pytest.mark.parametrize("n,errors,trusted", [(19, 0, False), (20, 2, True), (20, 3, False)])
def test_threshold_boundaries(session, taxonomy, n, errors, trusted):
    seed(session, taxonomy, n=n, disagreements=errors)
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.trusted is trusted
    assert report.metrics["difficulty"].observations == n


def test_null_corrections_are_not_implicit_confirmations(session, taxonomy):
    seed(session, taxonomy, explicit=False)
    report = judge_trust(session, question(session, taxonomy), [])
    assert not report.trusted
    assert all(
        metric.observations == 0
        for name, metric in report.metrics.items()
        if name != "acceptance"
    )
    assert report.metrics["acceptance"].observations == 20


@pytest.mark.parametrize("change", ["style", "taxonomy", "model", "rubric"])
def test_scope_isolation(session, taxonomy, change):
    seed(session, taxonomy)
    options = {}
    if change == "style":
        options["style"] = "py.fix_bug"
    elif change == "taxonomy":
        other = CurriculumVersionRow(label="v2", course_id=taxonomy.course_id)
        other.topics.append(TopicRow(name="Other", subtopics=[SubtopicRow(name="other")]))
        session.add(other)
        session.flush()
        taxonomy = other
    else:
        options[change] = "changed"
    report = judge_trust(session, question(session, taxonomy, **options), [])
    assert not report.trusted
    assert report.metrics["difficulty"].observations == 0


def test_exact_tenth_audits_persist_and_auto_approvals_add_no_evidence(session, taxonomy, engine):
    seed(session, taxonomy)
    ids = []
    for i in range(1, 22):
        row = question(session, taxonomy)
        expected = "audit" if i % 10 == 0 else "auto_approved"
        assert route_generated_question(session, row, []) == expected
        assert row.trust_sequence == i
        assert route_generated_question(session, row, []) == expected
        assert row.status == (
            QuestionStatus.VALIDATION_PASSED if expected == "audit" else QuestionStatus.APPROVED
        )
        ids.append(row.id)
    session.commit()
    with Session(engine) as reopened:
        assert reopened.get(QuestionRow, ids[9]).trust_provenance == "audit"
        assert reopened.scalar(select(JudgeTrustCounterRow.eligible_count)) == 21
        report = judge_trust(reopened, reopened.get(QuestionRow, ids[-1]), [])
        assert report.metrics["difficulty"].observations == 20
        assert len(list(reopened.scalars(select(ProfessorReviewRow)))) == 20


def test_a_question_held_for_review_is_pending_even_in_a_trusted_scope(session, taxonomy):
    """A round duplicate kept on its last attempt (ADR-063 point 6) waits for the professor."""
    seed(session, taxonomy)
    row = question(session, taxonomy)
    assert judge_trust(session, row, []).trusted
    assert route_generated_question(session, row, [], hold_for_review=True) == "pending"
    assert row.status == QuestionStatus.VALIDATION_PASSED
    assert row.trust_sequence is None
    assert session.scalar(select(JudgeTrustCounterRow.eligible_count)) is None
    assert route_generated_question(session, question(session, taxonomy), []) == "auto_approved"


def test_audit_disagreement_revokes_immediately_and_agreement_recovers(session, taxonomy):
    seed(session, taxonomy)
    for _ in range(10):
        audit = question(session, taxonomy)
        route_generated_question(session, audit, [])
    assert audit.trust_provenance == "audit"
    review(session, audit, agrees=False)
    row = question(session, taxonomy)
    report = judge_trust(session, row, [])
    assert report.metrics["difficulty"].agreement_rate == 0.95
    assert report.metrics["difficulty"].audit_revoked
    assert not report.trusted
    assert route_generated_question(session, row, []) == "pending"
    review(session, row)
    assert not judge_trust(session, question(session, taxonomy), []).trusted
    seed(session, taxonomy, n=18)
    assert not judge_trust(session, question(session, taxonomy), []).trusted
    seed(session, taxonomy, n=1)
    assert judge_trust(session, question(session, taxonomy), []).trusted


def test_recent_errors_replace_old_evidence(session, taxonomy):
    seed(session, taxonomy, n=40)
    seed(session, taxonomy, n=3, disagreements=3)
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["difficulty"].observations == 20
    assert report.metrics["difficulty"].agreement_rate == 0.85
    assert not report.trusted


def test_audit_rejection_without_corrections_revokes_without_inventing_observations(
    session,
    taxonomy,
):
    seed(session, taxonomy)
    for _ in range(10):
        audit = question(session, taxonomy)
        route_generated_question(session, audit, [])
    review(session, audit, explicit=False, decision=ReviewDecision.REJECT)
    candidate = question(session, taxonomy)
    report = judge_trust(session, candidate, [])
    assert report.metrics["difficulty"].observations == 20
    assert report.metrics["difficulty"].agreement_rate == 1.0
    assert not report.trusted
    route_generated_question(session, candidate, [])
    review(session, candidate)
    assert not judge_trust(session, question(session, taxonomy), []).trusted
    seed(session, taxonomy, n=19)
    assert judge_trust(session, question(session, taxonomy), []).trusted


def test_repeated_reviews_do_not_manufacture_twenty_observations(session, taxonomy):
    row = question(session, taxonomy)
    route_generated_question(session, row, [])
    review(session, row, agrees=False)
    for _ in range(20):
        review(session, row)
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["difficulty"].observations == 1
    assert report.metrics["difficulty"].agreements == 0
    assert not report.trusted


def test_nullable_corrections_remain_null_after_refresh(session, taxonomy):
    row = question(session, taxonomy)
    record = ProfessorReviewRow(question_id=row.id, decision=ReviewDecision.APPROVE)
    session.add(record)
    session.flush()
    session.refresh(record)
    assert record.corrected_subtopic_ids is None
    assert session.scalar(text("SELECT corrected_subtopic_ids_json FROM professor_reviews")) is None


def test_extra_enabled_judge_requires_manual_review(session, taxonomy, monkeypatch):
    seed(session, taxonomy)
    monkeypatch.setenv("JUDGE_METRICS_ENABLED", "difficulty,subtopic,issues")
    get_settings.cache_clear()
    row = question(session, taxonomy)
    evaluation = deepcopy(row.pedagogical_eval)
    evaluation["metrics"].append({"metric": "issues", "status": "completed", "passed": True})
    row.pedagogical_eval = evaluation
    report = judge_trust(session, row, [])
    assert report.trusted
    assert not report.eligible
    assert route_generated_question(session, row, []) == "pending"


def test_legacy_reviews_pair_with_preceding_history_not_later_rejudge(session, taxonomy):
    row = question(session, taxonomy)
    row.spec = {
        "difficulty": "easy",
        "topic_id": row.topic_id,
        "subtopic_ids": list(row.subtopic_ids),
    }
    session.add(
        QuestionEvaluationRow(
            question_id=row.id,
            evaluation=row.pedagogical_eval,
            judge_model="judge-v1",
            rubric_version="r1",
            run_id="before",
        )
    )
    session.flush()
    review(session, row)
    session.add(
        QuestionEvaluationRow(
            question_id=row.id,
            evaluation={**row.pedagogical_eval, "judge_model": "judge-v2"},
            judge_model="judge-v2",
            rubric_version="r1",
            run_id="after",
        )
    )
    session.flush()
    assert (
        judge_trust(session, question(session, taxonomy), []).metrics["difficulty"].agreements == 1
    )
    assert (
        judge_trust(session, question(session, taxonomy, model="judge-v2"), [])
        .metrics["difficulty"]
        .observations
        == 0
    )


def test_legacy_missing_original_topic_does_not_use_current_classification(session, taxonomy):
    row = question(session, taxonomy)
    session.add(
        QuestionEvaluationRow(question_id=row.id, evaluation=row.pedagogical_eval, run_id="legacy")
    )
    session.flush()
    review(session, row)
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["subtopic"].observations == 0
    # An explicit immutable difficulty verdict still supports its own metric.
    assert report.metrics["difficulty"].observations == 1


def test_legacy_passing_fallback_uses_frozen_spec(session, taxonomy):
    row = question(session, taxonomy)
    row.spec = {
        "difficulty": "easy",
        "topic_id": row.topic_id,
        "subtopic_ids": list(row.subtopic_ids),
    }
    evaluation = deepcopy(row.pedagogical_eval)
    for metric in evaluation["metrics"]:
        for key in ("proposed_difficulty", "proposed_topic_id", "proposed_subtopic_ids"):
            metric.pop(key, None)
    row.pedagogical_eval = evaluation
    session.add(QuestionEvaluationRow(question_id=row.id, evaluation=evaluation, run_id="legacy"))
    session.flush()
    review(session, row)
    row.difficulty = Difficulty.HARD
    row.topic_id = None
    row.subtopic_ids = []
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["difficulty"].agreements == 1
    assert report.metrics["subtopic"].agreements == 1


def test_professor_agrees_with_judge_that_corrected_generator_topic(session, taxonomy):
    corrected_topic = TopicRow(
        curriculum_version_id=taxonomy.id,
        name="Correct topic",
        subtopics=[SubtopicRow(name="Correct subtopic")],
    )
    session.add(corrected_topic)
    session.flush()
    row = question(session, taxonomy)
    evaluation = deepcopy(row.pedagogical_eval)
    evaluation["metrics"][1].update(
        passed=False,
        proposed_topic_id=corrected_topic.id,
        proposed_subtopic_ids=[corrected_topic.subtopics[0].id],
    )
    row.pedagogical_eval = evaluation
    route_generated_question(session, row, [])
    session.add(
        ProfessorReviewRow(
            question_id=row.id,
            decision=ReviewDecision.APPROVE,
            corrected_subtopic_ids=[corrected_topic.subtopics[0].id],
        )
    )
    session.flush()
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["subtopic"].observations == 1
    assert report.metrics["subtopic"].agreements == 1


@pytest.mark.parametrize("failure", ["missing", "failed", "error", "overall_partial"])
def test_current_verdicts_must_pass_and_complete(session, taxonomy, failure):
    seed(session, taxonomy)
    row = question(session, taxonomy)
    evaluation = deepcopy(row.pedagogical_eval)
    if failure == "missing":
        evaluation["metrics"] = evaluation["metrics"][:1]
    elif failure == "failed":
        evaluation["metrics"][0]["passed"] = False
    elif failure == "error":
        evaluation["metrics"][0]["status"] = "error"
    else:
        evaluation["status"] = "partial"
    row.pedagogical_eval = evaluation
    assert not judge_trust(session, row, []).eligible
    assert route_generated_question(session, row, []) == "pending"
    assert session.scalar(select(JudgeTrustCounterRow.eligible_count)) is None


def test_custom_rules_need_answered_explicit_reviews_and_new_versions(session, taxonomy):
    rule = CustomJudgeRow(
        curriculum_version_id=taxonomy.id,
        rule_text="No globals",
        kind=CustomJudgeKind.PATTERN,
        pattern="ast:Global",
    )
    session.add(rule)
    session.flush()
    results = [
        {"judge_id": rule.id, "rule_text": rule.rule_text, "kind": "pattern", "passed": True}
    ]
    seed(session, taxonomy, custom=results)
    row = question(session, taxonomy)
    assert judge_trust(session, row, results).trusted
    assert not judge_trust(session, row, []).eligible
    unanswered = [{**results[0], "passed": None}]
    assert not judge_trust(session, row, unanswered).eligible
    route_generated_question(session, row, results)
    review(session, row, decision=ReviewDecision.REJECT)
    assert (
        judge_trust(session, question(session, taxonomy), results)
        .metrics[f"custom:{rule.id}"]
        .agreements
        == 19
    )
    rule.pattern = "ast:Nonlocal"
    assert not judge_trust(session, question(session, taxonomy), results).trusted
    rule.pattern = "ast:Global"
    rule.updated_at = datetime.now(UTC)
    assert not judge_trust(session, question(session, taxonomy), results).trusted
    rule.rule_text = "New text"
    results[0]["rule_text"] = rule.rule_text
    assert (
        judge_trust(session, question(session, taxonomy), results)
        .metrics[f"custom:{rule.id}"]
        .observations
        == 0
    )


def test_passing_verdict_fallback_is_frozen_before_professor_edits(session, taxonomy):
    row = question(session, taxonomy)
    evaluation = deepcopy(row.pedagogical_eval)
    for metric in evaluation["metrics"]:
        metric.pop("proposed_difficulty", None)
        metric.pop("proposed_subtopic_ids", None)
        metric.pop("proposed_topic_id", None)
    row.pedagogical_eval = evaluation
    route_generated_question(session, row, [])
    review(session, row)
    row.difficulty = Difficulty.HARD
    row.pedagogical_eval = {"status": "error", "judge_model": "new", "rubric_version": "new"}
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["difficulty"].agreements == 1
    assert report.metrics["subtopic"].agreements == 1


def test_concurrent_sessions_have_unique_sequences(session, taxonomy, engine):
    seed(session, taxonomy)
    rows = [question(session, taxonomy) for _ in range(12)]
    ids = [row.id for row in rows]
    session.commit()

    def route(identifier):
        with Session(engine) as worker:
            row = worker.get(QuestionRow, identifier)
            route_generated_question(worker, row, [])
            worker.commit()
            return row.trust_sequence, row.trust_provenance

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(route, ids))
    assert sorted(sequence for sequence, _ in results) == list(range(1, 13))
    assert sum(provenance == "audit" for _, provenance in results) == 1


def test_counter_and_routing_rollback_together(session, taxonomy, engine):
    seed(session, taxonomy)
    row = question(session, taxonomy)
    identifier = row.id
    session.commit()
    assert route_generated_question(session, row, []) == "auto_approved"
    session.rollback()
    with Session(engine) as reopened:
        row = reopened.get(QuestionRow, identifier)
        assert row.trust_provenance is None
        assert reopened.scalar(select(JudgeTrustCounterRow.eligible_count)) is None
        route_generated_question(reopened, row, [])
        assert row.trust_sequence == 1


def test_sqlite_0005_upgrade_preserves_rows_and_adds_only_trust_schema(engine):
    with engine.begin() as connection:
        command.downgrade(_alembic_config(connection), "0005_question_setup")
        connection.execute(
            text(
                "INSERT INTO questions (kind,difficulty,status,prompt,"
                "generator_kind,generator_name,generator_version,priority,times_used,created_at) "
                "VALUES ('discrete','easy','generated','Old','base','g','1',0,0,'2026-01-01')"
            )
        )
    init_db(engine)
    verify_schema(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("questions")}
    assert {
        "trust_provenance",
        "trust_scope_key",
        "trust_sequence",
        "trust_snapshot_json",
    } <= columns
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0014_question_embeddings"
        )
        assert connection.execute(text("SELECT prompt,trust_provenance FROM questions")).one() == (
            "Old",
            None,
        )


def seed_decisions(session, taxonomy, decisions):
    for decision in decisions:
        row = question(session, taxonomy)
        route_generated_question(session, row, [])
        review(session, row, decision=decision)


@pytest.mark.parametrize("rejects,trusted", [(2, True), (3, False)])
def test_rejects_block_trust_even_when_judges_agree(session, taxonomy, rejects, trusted):
    seed_decisions(
        session,
        taxonomy,
        [ReviewDecision.REJECT] * rejects + [ReviewDecision.APPROVE] * (20 - rejects),
    )
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["difficulty"].agreement_rate == 1.0
    assert report.metrics["acceptance"].observations == 20
    assert report.metrics["acceptance"].agreements == 20 - rejects
    assert report.trusted is trusted


def test_an_edit_is_not_an_acceptance(session, taxonomy):
    seed_decisions(session, taxonomy, [ReviewDecision.EDIT] * 3 + [ReviewDecision.APPROVE] * 17)
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["acceptance"].agreements == 17
    assert not report.trusted


def test_acceptance_window_needs_the_minimum_observations(session, taxonomy):
    seed_decisions(session, taxonomy, [ReviewDecision.APPROVE] * 19)
    report = judge_trust(session, question(session, taxonomy), [])
    assert not report.metrics["acceptance"].trusted
