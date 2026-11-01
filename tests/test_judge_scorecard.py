"""Per-judge scorecard (ADR-064, m8): agreement, κ, Wilson range, retries and drops."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calibration import (
    SCORECARD_METRICS,
    build_judge_scorecard,
    cohen_kappa,
    score_from_counts,
    wilson_interval,
)
from app.domain.enums import Difficulty, JudgeMetricId, RejectionReason, ReviewDecision
from app.domain.questions import GenerationAttempt, QuestionCheck
from app.evaluation.schema import MetricResult, evaluation_from_metrics
from app.feedback import submit_review
from app.persistence.models import (
    CurriculumVersionRow,
    GenerationRoundRow,
    QuestionRow,
    QuestionSetupRow,
    SubtopicRow,
    TopicRow,
)

DIFFICULTY = JudgeMetricId.DIFFICULTY
SUBTOPIC = JudgeMetricId.SUBTOPIC
ISSUES = JudgeMetricId.ISSUES


def _evaluation(
    *,
    difficulty: Difficulty = Difficulty.EASY,
    difficulty_passed: bool = True,
    subtopic_ids: list[int] | None = None,
    subtopic_passed: bool = True,
    issues_passed: bool = True,
) -> dict:
    metrics = [
        MetricResult(metric=ISSUES, passed=issues_passed, rationale="issues", issue_codes=[]),
        MetricResult(
            metric=DIFFICULTY,
            passed=difficulty_passed,
            rationale="difficulty",
            proposed_difficulty=difficulty,
        ),
        MetricResult(
            metric=SUBTOPIC,
            passed=subtopic_passed,
            rationale="subtopic",
            proposed_subtopic_ids=list(subtopic_ids or []),
        ),
        MetricResult(metric=JudgeMetricId.GENERATABILITY, passed=True, rationale="ok"),
    ]
    return evaluation_from_metrics(metrics, question_id=None, judge_model="fake").model_dump(
        mode="json"
    )


def _taxonomy(session: Session) -> tuple[CurriculumVersionRow, TopicRow, list[SubtopicRow]]:
    version = CurriculumVersionRow(label="Intro")
    session.add(version)
    session.flush()
    topic = TopicRow(name="Loops", curriculum_version_id=version.id, position=0)
    session.add(topic)
    session.flush()
    subs = [
        SubtopicRow(name="For", topic_id=topic.id, position=0),
        SubtopicRow(name="While", topic_id=topic.id, position=1),
    ]
    session.add_all(subs)
    session.commit()
    return version, topic, subs


def _question(
    session: Session,
    *,
    version: CurriculumVersionRow | None = None,
    topic: TopicRow | None = None,
    subtopic_ids: list[int] | None = None,
    difficulty: Difficulty = Difficulty.EASY,
    evaluation: dict | None = None,
    spec: dict | None = None,
) -> QuestionRow:
    ids = list(subtopic_ids or [])
    row = QuestionRow(
        prompt="Write a loop.",
        original_prompt="Write a loop.",
        curriculum_version_id=version.id if version is not None else None,
        topic_id=topic.id if topic is not None else None,
        subtopic_ids=ids,
        difficulty=difficulty,
        spec=spec if spec is not None else {"difficulty": difficulty.value, "subtopic_ids": ids},
        pedagogical_eval=evaluation if evaluation is not None else _evaluation(subtopic_ids=ids),
    )
    session.add(row)
    session.commit()
    return row


def _review(
    session: Session,
    question: QuestionRow,
    *,
    decision: ReviewDecision = ReviewDecision.APPROVE,
    reasons: list[RejectionReason] | None = None,
    corrected_difficulty: Difficulty | None = None,
    corrected_subtopic_ids: list[int] | None = None,
) -> None:
    submit_review(
        session,
        question_id=question.id,
        decision=decision,
        reasons=reasons,
        corrected_difficulty=corrected_difficulty,
        corrected_subtopic_ids=corrected_subtopic_ids,
    )
    session.commit()


def _row_for(report, metric: JudgeMetricId):
    return next(row for row in report.judges if row.metric is metric)


def _failed(name: str) -> QuestionCheck:
    return QuestionCheck(name=name, passed=False, deterministic=False, detail=name)


def _round(session: Session, version: CurriculumVersionRow) -> GenerationRoundRow:
    setup = QuestionSetupRow(curriculum_version_id=version.id)
    session.add(setup)
    session.flush()
    row = GenerationRoundRow(setup_id=setup.id, number=1)
    session.add(row)
    session.commit()
    return row


# ------------------------------------------------------------------ arithmetic


def test_wilson_interval_and_kappa_on_fixed_counts() -> None:
    assert wilson_interval(8, 10) == (0.4902, 0.9433)
    assert wilson_interval(0, 0) is None
    assert cohen_kappa(20, 5, 10, 15) == 0.4
    assert cohen_kappa(10, 0, 0, 0) is None


def test_score_from_counts_fills_the_wilson_range_and_flag_rate() -> None:
    row = score_from_counts(
        DIFFICULTY,
        n=10,
        agreements=8,
        true_neg=7,
        false_pos=1,
        false_neg=2,
        true_pos=0,
    )
    assert (row.agreement, row.agreement_low, row.agreement_high) == (0.8, 0.4902, 0.9433)
    assert (row.missed, row.false_alarms, row.flags, row.flag_rate) == (2, 1, 1, 0.1)
    assert row.kappa == cohen_kappa(7, 1, 2, 0)


def test_an_empty_bank_reports_three_judges_with_no_rates(session: Session) -> None:
    report = build_judge_scorecard(session)
    assert [row.metric for row in report.judges] == list(SCORECARD_METRICS)
    for row in report.judges:
        assert (row.n, row.agreement, row.kappa, row.retries, row.drops) == (0, None, None, 0, 0)


# ------------------------------------------------------- difficulty / subtopic


def test_difficulty_is_scored_against_corrected_difficulty_on_every_review(
    session: Session,
) -> None:
    """A confirmation that does not cite TOO_EASY still counts (unlike reason-only calibration)."""
    version, topic, subs = _taxonomy(session)
    matching = _question(
        session,
        version=version,
        topic=topic,
        subtopic_ids=[subs[0].id],
        evaluation=_evaluation(difficulty=Difficulty.EASY, subtopic_ids=[subs[0].id]),
    )
    _review(session, matching, corrected_difficulty=Difficulty.EASY)
    missed = _question(
        session,
        version=version,
        topic=topic,
        subtopic_ids=[subs[0].id],
        evaluation=_evaluation(difficulty=Difficulty.EASY, subtopic_ids=[subs[0].id]),
    )
    _review(session, missed, corrected_difficulty=Difficulty.HARD)

    report = build_judge_scorecard(session)
    difficulty = _row_for(report, DIFFICULTY)
    assert (difficulty.n, difficulty.agreements, difficulty.missed) == (2, 1, 1)
    assert difficulty.agreement == 0.5
    assert difficulty.false_alarms == 0


def test_subtopic_is_scored_against_corrected_subtopic_ids(session: Session) -> None:
    version, topic, subs = _taxonomy(session)
    matching = _question(
        session,
        version=version,
        topic=topic,
        subtopic_ids=[subs[0].id],
        evaluation=_evaluation(subtopic_ids=[subs[0].id]),
    )
    _review(session, matching, corrected_subtopic_ids=[subs[0].id])
    missed = _question(
        session,
        version=version,
        topic=topic,
        subtopic_ids=[subs[0].id],
        evaluation=_evaluation(subtopic_ids=[subs[0].id]),
    )
    _review(session, missed, corrected_subtopic_ids=[subs[1].id])

    subtopic = _row_for(build_judge_scorecard(session), SUBTOPIC)
    assert (subtopic.n, subtopic.agreements, subtopic.missed) == (2, 1, 1)


def test_a_judge_that_flagged_the_requested_level_the_professor_kept_is_a_false_alarm(
    session: Session,
) -> None:
    version, topic, subs = _taxonomy(session)
    row = _question(
        session,
        version=version,
        topic=topic,
        subtopic_ids=[subs[0].id],
        difficulty=Difficulty.EASY,
        evaluation=_evaluation(
            difficulty=Difficulty.HARD,
            difficulty_passed=False,
            subtopic_ids=[subs[0].id],
        ),
    )
    _review(session, row, corrected_difficulty=Difficulty.EASY)

    difficulty = _row_for(build_judge_scorecard(session), DIFFICULTY)
    assert (difficulty.n, difficulty.agreements, difficulty.false_alarms) == (1, 0, 1)
    assert difficulty.flag_rate == 1.0


def test_a_borderline_keep_is_a_scorecard_observation_and_a_borderline_episode(
    session: Session,
) -> None:
    from app.memory import SOURCE_BORDERLINE
    from app.persistence.models import MemoryEpisodeRow

    version, topic, subs = _taxonomy(session)
    row = _question(
        session,
        version=version,
        topic=topic,
        subtopic_ids=[subs[0].id],
        difficulty=Difficulty.MEDIUM,
        spec={
            "difficulty": Difficulty.MEDIUM.value,
            "subtopic_ids": [subs[0].id],
        },
        evaluation=_evaluation(
            difficulty=Difficulty.HARD,
            difficulty_passed=False,
            subtopic_ids=[subs[0].id],
        ),
    )
    row.target_subtopic_id = subs[0].id
    session.commit()
    _review(session, row, corrected_difficulty=Difficulty.MEDIUM)

    difficulty = _row_for(build_judge_scorecard(session), DIFFICULTY)
    assert (difficulty.n, difficulty.false_alarms) == (1, 1)
    episode = session.scalars(
        select(MemoryEpisodeRow).where(MemoryEpisodeRow.question_id == row.id)
    ).one()
    assert episode.source == SOURCE_BORDERLINE


# ------------------------------------------------------- issues / agreement


def test_issues_agreement_uses_the_professor_reason_codes(session: Session) -> None:
    version, topic, subs = _taxonomy(session)
    clean = _question(session, version=version, topic=topic, subtopic_ids=[subs[0].id])
    _review(session, clean)
    missed = _question(
        session,
        version=version,
        topic=topic,
        subtopic_ids=[subs[0].id],
        evaluation=_evaluation(issues_passed=True, subtopic_ids=[subs[0].id]),
    )
    _review(
        session,
        missed,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TECHNICALLY_INCORRECT],
    )

    issues = _row_for(build_judge_scorecard(session), ISSUES)
    assert (issues.n, issues.agreements, issues.missed) == (2, 1, 1)


# ------------------------------------------------------- retries / drops


def test_retries_and_drops_are_attributed_from_generation_attempts(session: Session) -> None:
    version, topic, subs = _taxonomy(session)
    round_row = _round(session, version)
    retried = _question(session, version=version, topic=topic, subtopic_ids=[subs[0].id])
    retried.round_id = round_row.id
    retried.generation_attempts = [
        GenerationAttempt(
            number=1,
            accepted=True,
            failed_checks=[_failed("difficulty_judge")],
        ),
        GenerationAttempt(number=2, accepted=True),
    ]
    dropped = _question(session, version=version, topic=topic, subtopic_ids=[subs[0].id])
    dropped.round_id = round_row.id
    dropped.generation_attempts = [
        GenerationAttempt(
            number=1,
            accepted=True,
            failed_checks=[_failed("topic_judge")],
        ),
        GenerationAttempt(
            number=2,
            accepted=True,
            failed_checks=[_failed("topic_judge"), _failed("duplicate")],
        ),
    ]
    session.commit()

    report = build_judge_scorecard(session)
    assert (_row_for(report, DIFFICULTY).retries, _row_for(report, DIFFICULTY).drops) == (1, 0)
    assert (_row_for(report, SUBTOPIC).retries, _row_for(report, SUBTOPIC).drops) == (1, 1)
    assert (_row_for(report, ISSUES).retries, _row_for(report, ISSUES).drops) == (0, 0)


def test_a_duplicate_check_is_not_a_judge_retry(session: Session) -> None:
    version, topic, subs = _taxonomy(session)
    round_row = _round(session, version)
    row = _question(session, version=version, topic=topic, subtopic_ids=[subs[0].id])
    row.round_id = round_row.id
    row.generation_attempts = [
        GenerationAttempt(number=1, accepted=True, failed_checks=[_failed("duplicate")]),
        GenerationAttempt(number=2, accepted=True),
    ]
    session.commit()
    report = build_judge_scorecard(session)
    assert all(row.retries == 0 and row.drops == 0 for row in report.judges)


# ------------------------------------------------------- API


def test_the_scorecard_endpoint_returns_the_three_judges(
    client: TestClient, session: Session
) -> None:
    body = client.get("/api/judges/scorecard").json()
    assert [row["metric"] for row in body["judges"]] == ["issues", "difficulty", "subtopic"]
    assert body["judges"][0]["agreement"] is None
    assert body["judges"][0]["kappa"] is None
    assert "retries" in body["judges"][0] and "drops" in body["judges"][0]
