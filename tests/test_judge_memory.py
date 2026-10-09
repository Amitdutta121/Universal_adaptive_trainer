"""MemAlign memory for the judges, frozen per round (ADR-064, m11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import (
    Difficulty,
    GuidelineStatus,
    JudgeMetricId,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.domain.questions import Question
from app.evaluation.judge_memory import (
    SnapshotScore,
    apply_judge_lessons,
    capture_snapshot,
    compose_judge_system,
    episode_confirms,
    episode_teaches,
    latest_promoted,
    memory_rubric_suffix,
    promote_snapshot,
)
from app.evaluation.judge_prompts import effective_rubric_version
from app.evaluation.prompts import RUBRIC_VERSION
from app.memory import SOURCE_AUDIT, SOURCE_BORDERLINE, SOURCE_RETRY, SOURCE_REVIEW, judge_target
from app.memory.guidelines import refusal_reason
from app.persistence.models import (
    JudgeMemorySnapshotRow,
    MemoryEpisodeRow,
    MemoryGuidelineRow,
    QuestionRow,
)
from app.persistence.repositories import QuestionRepository, ReviewOutcomeRepository
from app.subjects import PYTHON_PROFILE

DIFFICULTY = JudgeMetricId.DIFFICULTY
ISSUES = JudgeMetricId.ISSUES
SUBTOPIC = JudgeMetricId.SUBTOPIC
SUBJECT = PYTHON_PROFILE.personal_key


def _question(session: Session, prompt: str = "What does this loop print?") -> QuestionRow:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt=prompt,
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.APPROVED,
        )
    )
    session.flush()
    return row


def _episode(
    session: Session,
    *,
    source: str = SOURCE_REVIEW,
    decision: ReviewDecision = ReviewDecision.APPROVE,
    reasons: list[RejectionReason] | None = None,
    prompt: str = "What does this loop print?",
    rationale: str = "easy is right",
    created_at: datetime | None = None,
    comment: str | None = None,
    verdicts: dict | None = None,
    corrected_difficulty: Difficulty | None = None,
    corrected_subtopic_ids: list[int] | None = None,
) -> MemoryEpisodeRow:
    question = _question(session, prompt)
    row = MemoryEpisodeRow(
        question_id=question.id,
        source=source,
        subject=SUBJECT,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=Difficulty.EASY,
        subtopic_ids=[5],
        text=prompt,
        decision=decision,
        reasons=reasons or [],
        comment=comment,
        corrected_difficulty=corrected_difficulty,
        corrected_subtopic_ids=corrected_subtopic_ids,
        judge_verdicts=verdicts
        or {DIFFICULTY.value: {"passed": True, "rationale": rationale, "status": "completed"}},
    )
    if created_at is not None:
        row.created_at = created_at
    session.add(row)
    session.flush()
    return row


def _guideline(session: Session, text: str, metric: JudgeMetricId = DIFFICULTY) -> None:
    session.add(
        MemoryGuidelineRow(
            target=judge_target(metric),
            subject=SUBJECT,
            text=text,
            review_ids=[1, 2],
            status=GuidelineStatus.ACTIVE,
            confirmed_by_professor=True,
        )
    )
    session.flush()


# ------------------------------------------------------------------ episodes


def _all_pass() -> dict:
    return {
        metric.value: {"passed": True, "status": "completed", "rationale": "fine"}
        for metric in (DIFFICULTY, SUBTOPIC, ISSUES)
    }


def test_a_distractor_complaint_is_no_evidence_for_difficulty_or_subtopic(
    session: Session,
) -> None:
    """The live misrouting: a reject with no reasons and unchanged corrections."""
    reject = _episode(
        session,
        decision=ReviewDecision.REJECT,
        comment="Ambiguous distractors: B and C are both defensible. Trivial recall.",
        verdicts=_all_pass(),
        corrected_difficulty=Difficulty.EASY,
        corrected_subtopic_ids=[5],
    )
    assert not episode_teaches(reject, DIFFICULTY)
    assert not episode_teaches(reject, SUBTOPIC)
    assert episode_teaches(reject, ISSUES)
    # The difficulty and subtopic judges agreed with the professor: confirmation only.
    assert episode_confirms(reject, DIFFICULTY)
    assert episode_confirms(reject, SUBTOPIC)
    assert not episode_confirms(reject, ISSUES)


def test_difficulty_learns_from_a_changed_level_or_a_difficulty_reason(
    session: Session,
) -> None:
    moved = _episode(session, verdicts=_all_pass(), corrected_difficulty=Difficulty.MEDIUM)
    proposed = _episode(
        session,
        verdicts={DIFFICULTY.value: {"passed": False, "proposed_difficulty": "hard"}},
    )
    reason = _episode(
        session,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
        verdicts=_all_pass(),
    )
    for episode in (moved, proposed, reason):
        assert episode_teaches(episode, DIFFICULTY)
        assert not episode_teaches(episode, SUBTOPIC)
    assert not episode_teaches(reason, ISSUES)


def test_subtopic_learns_from_changed_subtopics_or_the_wrong_topic_reason(
    session: Session,
) -> None:
    moved = _episode(session, verdicts=_all_pass(), corrected_subtopic_ids=[6])
    proposed = _episode(
        session,
        verdicts={SUBTOPIC.value: {"passed": False, "proposed_subtopic_ids": [7]}},
    )
    reason = _episode(
        session,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.WRONG_TOPIC_SUBTOPIC],
        verdicts=_all_pass(),
    )
    for episode in (moved, proposed, reason):
        assert episode_teaches(episode, SUBTOPIC)
        assert not episode_teaches(episode, DIFFICULTY)
    assert not episode_teaches(reason, ISSUES)


def test_issues_learn_from_issue_reasons_unattributed_comments_and_false_alarms(
    session: Session,
) -> None:
    issue_reject = _episode(
        session,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TECHNICALLY_INCORRECT],
        verdicts=_all_pass(),
    )
    edit_comment = _episode(
        session, decision=ReviewDecision.EDIT, comment="Wording", verdicts=_all_pass()
    )
    false_alarm = _episode(
        session,
        decision=ReviewDecision.APPROVE,
        verdicts={ISSUES.value: {"passed": False}},
    )
    agreed = _episode(session, decision=ReviewDecision.APPROVE, verdicts=_all_pass())
    silent_reject = _episode(session, decision=ReviewDecision.REJECT, verdicts=_all_pass())
    easy_reject = _episode(
        session,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
        comment="Too easy",
        verdicts=_all_pass(),
    )
    audit = _episode(
        session,
        source=SOURCE_AUDIT,
        decision=ReviewDecision.APPROVE,
        verdicts={ISSUES.value: {"passed": False}},
    )
    borderline = _episode(
        session,
        source=SOURCE_BORDERLINE,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.POOR_DISTRACTORS],
    )
    retry = _episode(session, source=SOURCE_RETRY, decision=ReviewDecision.APPROVE)

    for episode in (issue_reject, edit_comment, false_alarm, audit, borderline):
        assert episode_teaches(episode, ISSUES)
    for episode in (agreed, silent_reject, easy_reject, retry):
        assert not episode_teaches(episode, ISSUES)
    assert episode_confirms(agreed, ISSUES)
    assert not episode_confirms(retry, ISSUES)
    for episode in (issue_reject, edit_comment, borderline):
        assert not episode_teaches(episode, DIFFICULTY)
        assert not episode_teaches(episode, SUBTOPIC)


def test_the_misrouted_reviews_distil_only_the_issues_judge(session: Session) -> None:
    from llm_fakes import judged

    from app.feedback import route_review_outcome, submit_review
    from app.memory.guidelines import GuidelineEdits

    systems: list[str] = []

    class Distiller:
        description = "fake/distiller"

        def complete_structured(self, *, system: str, prompt: str, response_model):
            systems.append(system)
            return GuidelineEdits()

    rows = []
    for _ in range(2):
        question = _question(session)
        question.pedagogical_eval = judged(question_id=question.id).model_dump(mode="json")
        session.commit()
        review = submit_review(
            session,
            question_id=question.id,
            decision=ReviewDecision.REJECT,
            comment="Assess the distractors: two are ambiguous.",
            corrected_difficulty=Difficulty.EASY,
        )
        route_review_outcome(session, review)
        session.commit()
        rows.append(ReviewOutcomeRepository(session).get_for_review(review.id))

    apply_judge_lessons(session, rows, PYTHON_PROFILE, client=Distiller())
    assert len(systems) == 1
    assert "(judge:issues)" in systems[0]


def test_difficulty_and_subtopic_guidelines_outside_their_scope_are_refused() -> None:
    assert refusal_reason("Assess questions for ambiguous distractors.", target="judge:difficulty")
    assert refusal_reason(
        "Ensure that distractors in multiple-choice questions are unambiguously incorrect.",
        target="judge:subtopic",
    )
    assert (
        refusal_reason("Pure recall of a keyword is easy, not medium.", target="judge:difficulty")
        is None
    )
    assert (
        refusal_reason(
            "A question on f-strings belongs to the String formatting subtopic.",
            target="judge:subtopic",
        )
        is None
    )
    assert (
        refusal_reason("Ensure distractors are unambiguously incorrect.", target="judge:issues")
        is None
    )


# ------------------------------------------------------------------ prompt


def test_the_judge_prompt_contains_guidelines_and_retrieved_episodes(session: Session) -> None:
    _guideline(session, "A counted loop alone is not hard.")
    _episode(
        session,
        prompt="How many times does range(3) run?",
        rationale="three iterations, still easy",
    )

    prompt = compose_judge_system(session, DIFFICULTY, PYTHON_PROFILE)
    assert "A counted loop alone is not hard." in prompt
    assert "How many times does range(3) run?" in prompt
    assert "three iterations, still easy" in prompt
    assert "Past cases for this judge" in prompt


def test_judges_in_a_round_ignore_memory_written_during_it(session: Session) -> None:
    before = datetime.now(UTC) - timedelta(minutes=5)
    _episode(
        session,
        prompt="Older reviewed loop question",
        rationale="older case",
        created_at=before,
    )
    snapshot = capture_snapshot(session, SUBJECT)
    snapshot.created_at = datetime.now(UTC) - timedelta(minutes=1)
    session.flush()
    _episode(
        session,
        prompt="Reviewed while this round was running",
        rationale="must not appear",
        created_at=datetime.now(UTC),
    )

    prompt = compose_judge_system(session, DIFFICULTY, PYTHON_PROFILE, snapshot=snapshot)
    assert "Older reviewed loop question" in prompt
    assert "Reviewed while this round was running" not in prompt
    assert "must not appear" not in prompt


def test_a_snapshot_that_lowers_held_out_agreement_is_not_promoted(session: Session) -> None:
    incumbent = capture_snapshot(session, SUBJECT)
    incumbent.promoted = True
    session.flush()
    candidate = capture_snapshot(session, SUBJECT)

    def scorer(row: JudgeMemorySnapshotRow) -> SnapshotScore:
        if row.id == incumbent.id:
            return SnapshotScore(agreement=0.80, known_bad_pass_rate=0.10)
        return SnapshotScore(agreement=0.60, known_bad_pass_rate=0.10)

    kept = promote_snapshot(session, candidate, scorer=scorer)
    assert kept.id == incumbent.id
    assert candidate.promoted is False
    assert latest_promoted(session, SUBJECT).id == incumbent.id


def test_trust_counters_continue_across_rounds_with_an_unchanged_snapshot(
    session: Session,
) -> None:
    snapshot = capture_snapshot(session, SUBJECT)
    promote_snapshot(session, snapshot)
    first = effective_rubric_version(session, snapshot_id=snapshot.id)
    second = effective_rubric_version(session, snapshot_id=snapshot.id)
    assert first == second
    assert first == f"{RUBRIC_VERSION}{memory_rubric_suffix(snapshot.id)}"
    assert first != RUBRIC_VERSION


def test_identical_guidelines_do_not_rename_the_panel(session: Session) -> None:
    assert apply_judge_lessons(session, [], PYTHON_PROFILE) is None
    snapshot = capture_snapshot(session, SUBJECT)
    promote_snapshot(session, snapshot)
    again = apply_judge_lessons(session, [], PYTHON_PROFILE)
    assert again is not None and again.id == snapshot.id


def test_judge_guidelines_may_mention_options_but_not_the_verdict_schema() -> None:
    kept = "Treat option A as a common misconception."
    assert refusal_reason(kept, target="judge:issues") is None
    assert (
        refusal_reason("Always return issue_codes as extra JSON fields.", target="judge:issues")
        is not None
    )
    assert refusal_reason("Always use four options.") is not None


def test_the_live_judge_renders_guidelines_onto_the_shipped_prompt(session: Session) -> None:
    from app.evaluation.prompts import JudgeContext
    from app.evaluation.service import PedagogicalJudge

    _guideline(session, "A counted loop alone is not hard.", ISSUES)
    seen: list[str] = []

    class RecordingClient:
        description = "fake/judge"

        def complete_structured(self, *, system: str, prompt: str, response_model):
            seen.append(system)
            raise RuntimeError("stop after recording")

    question = Question.model_validate(_question(session, "Write a counted loop."))
    judge = PedagogicalJudge(session, client=RecordingClient())
    context = JudgeContext(
        question_artifact={"prompt": question.prompt},
        source_sections=[],
        taxonomy=[],
        claimed_taxonomy={},
        requested_difficulty="easy",
        requested_question_type="multiple_choice",
    )
    with pytest.raises(RuntimeError):
        judge._run_metric(ISSUES, context, question, "You judge issues.")
    assert seen
    assert seen[0].startswith("You judge issues.")
    assert "A counted loop alone is not hard." in seen[0]


def test_replay_judges_smoke_with_stored_episodes(session: Session) -> None:
    """The paid replay is written; this path scores stored verdicts only."""
    from scripts.replay_judges import score_from_store

    _episode(session, decision=ReviewDecision.APPROVE)
    _episode(
        session,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
        rationale="called it easy",
    )
    table = score_from_store(session)
    assert DIFFICULTY.value in table
    assert table[DIFFICULTY.value]["n"] >= 1
