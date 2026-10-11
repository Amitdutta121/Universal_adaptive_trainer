"""Audit sample of judge-rejected drafts (ADR-064, m9)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_rounds import (
    LIBRARY,
    DifficultySequenceClient,
    KeywordEmbedder,
    _mcq,
    _queue,
    _run,
    _setup,
    _target,
)

from app.calibration import build_judge_scorecard
from app.config import Settings
from app.domain.enums import (
    CurriculumStatus,
    Difficulty,
    JudgeMetricId,
    QuestionStatus,
    ReviewDecision,
)
from app.evaluation.schema import MetricResult, evaluation_from_metrics
from app.feedback import submit_review
from app.generation import rounds as rounds_module
from app.generation.attempts import MAX_GENERATION_ATTEMPTS
from app.ingestion import BookImportService
from app.memory import SOURCE_AUDIT
from app.persistence.models import (
    CurriculumVersionRow,
    MemoryEpisodeRow,
    QuestionRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import BookStructureRepository, QuestionRepository
from app.retrieval import SectionEmbeddingStore


@pytest.fixture(autouse=True)
def fake_library(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.styles

    monkeypatch.setattr(rounds_module, "get_library", lambda subject: list(LIBRARY))
    monkeypatch.setattr(app.styles, "get_library", lambda subject: list(LIBRARY))


def _book(session: Session, settings: Settings):
    sections = [
        "A while loop repeats while a condition holds. Use a while loop to loop again.",
        "A string can be sliced. Take a slice of a string. string slice string.",
    ]
    doc = {
        "schema_version": "1",
        "title": "Audit Book",
        "chapters": [{"sections": [{"text": text} for text in sections]}],
    }
    book = BookImportService(session, settings).import_upload(
        filename="audit_book.json", data=docs.to_bytes(doc)
    )
    session.commit()
    return book


@pytest.fixture
def env(session: Session, settings: Settings) -> SimpleNamespace:
    book = _book(session, settings)
    version = CurriculumVersionRow(
        label="Audit v1",
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
        source_book_ids=[book.id],
    )
    session.add(version)
    session.flush()
    loops = TopicRow(curriculum_version_id=version.id, name="Loops", position=0)
    strings = TopicRow(curriculum_version_id=version.id, name="Strings", position=1)
    session.add_all([loops, strings])
    session.flush()
    while_loops = SubtopicRow(
        topic_id=loops.id, name="While loops", description="Using a while loop.", position=0
    )
    slicing = SubtopicRow(
        topic_id=strings.id, name="Slicing", description="Taking a slice of a string.", position=0
    )
    session.add_all([while_loops, slicing])
    session.commit()
    SectionEmbeddingStore(session, KeywordEmbedder()).backfill()
    session.commit()
    sections = BookStructureRepository(session).sections_in_book(book.id)
    return SimpleNamespace(
        version=version,
        while_loops=while_loops,
        slicing=slicing,
        sections=sections,
        book=book,
    )


def _audits(engine: Engine, round_id: int) -> list[QuestionRow]:
    with Session(engine) as fresh:
        return list(
            fresh.scalars(
                select(QuestionRow).where(
                    QuestionRow.round_id == round_id, QuestionRow.audit.is_(True)
                )
            )
        )


def _evaluation(*, difficulty_passed: bool, proposed: Difficulty, subtopic_ids: list[int]) -> dict:
    metrics = [
        MetricResult(metric=JudgeMetricId.ISSUES, passed=True, rationale="ok"),
        MetricResult(
            metric=JudgeMetricId.DIFFICULTY,
            passed=difficulty_passed,
            rationale="this is hard, not easy",
            proposed_difficulty=proposed,
        ),
        MetricResult(
            metric=JudgeMetricId.SUBTOPIC,
            passed=True,
            rationale="ok",
            proposed_subtopic_ids=list(subtopic_ids),
        ),
        MetricResult(metric=JudgeMetricId.GENERATABILITY, passed=True, rationale="ok"),
    ]
    return evaluation_from_metrics(metrics, question_id=None, judge_model="fake").model_dump(
        mode="json"
    )


def _audit_question(
    session: Session,
    *,
    version: CurriculumVersionRow,
    topic: TopicRow,
    subtopic_ids: list[int],
    difficulty: Difficulty = Difficulty.EASY,
) -> QuestionRow:
    row = QuestionRow(
        prompt="Write a loop.",
        original_prompt="Write a loop.",
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=list(subtopic_ids),
        difficulty=difficulty,
        status=QuestionStatus.VALIDATION_PASSED,
        spec={"difficulty": difficulty.value, "subtopic_ids": list(subtopic_ids)},
        pedagogical_eval=_evaluation(
            difficulty_passed=False, proposed=Difficulty.HARD, subtopic_ids=subtopic_ids
        ),
        audit=True,
        audit_metric="difficulty",
        audit_reason="this is hard, not easy",
    )
    session.add(row)
    session.commit()
    return row


def test_a_dropped_judge_failure_stores_one_audit_draft(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "easy", 3)])
    row = _queue(session, setup, [_target(env, "easy")])
    client = DifficultySequenceClient(
        difficulties=[Difficulty.HARD],
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
    )

    _run(engine, row.id, client)

    audits = _audits(engine, row.id)
    assert len(audits) == 1
    assert audits[0].audit_metric == "difficulty"
    assert audits[0].audit_reason
    assert audits[0].status is not QuestionStatus.APPROVED
    with Session(engine) as fresh:
        done = fresh.get(type(row), row.id)
        assert (done.produced, done.dropped) == (0, 1)


def test_a_round_keeps_at_most_two_audit_drafts(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "easy", 3)])
    row = _queue(session, setup, [_target(env, "easy"), _target(env, "easy"), _target(env, "easy")])
    client = DifficultySequenceClient(
        difficulties=[Difficulty.HARD],
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
    )

    _run(engine, row.id, client)

    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS * 3
    assert len(_audits(engine, row.id)) == 2


def test_a_kept_question_that_retried_a_judge_still_leaves_an_audit(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "easy", 3)])
    row = _queue(session, setup, [_target(env, "easy")])
    client = DifficultySequenceClient(
        difficulties=[Difficulty.HARD, Difficulty.EASY],
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
    )

    _run(engine, row.id, client)

    audits = _audits(engine, row.id)
    assert len(audits) == 1
    assert audits[0].audit_metric == "difficulty"
    with Session(engine) as fresh:
        kept = list(
            fresh.scalars(
                select(QuestionRow).where(
                    QuestionRow.round_id == row.id, QuestionRow.audit.is_(False)
                )
            )
        )
        assert len(kept) == 1
        done = fresh.get(type(row), row.id)
        assert (done.produced, done.dropped) == (1, 0)


def test_agree_is_a_confirmed_objection_and_disagree_is_a_false_alarm(session: Session) -> None:
    version = CurriculumVersionRow(label="Audit scorecard")
    session.add(version)
    session.flush()
    topic = TopicRow(name="Loops", curriculum_version_id=version.id, position=0)
    session.add(topic)
    session.flush()
    sub = SubtopicRow(name="For", topic_id=topic.id, position=0)
    session.add(sub)
    session.commit()

    confirmed = _audit_question(session, version=version, topic=topic, subtopic_ids=[sub.id])
    submit_review(
        session,
        question_id=confirmed.id,
        decision=ReviewDecision.REJECT,
        corrected_difficulty=Difficulty.HARD,
        corrected_subtopic_ids=[sub.id],
    )
    session.commit()

    false_alarm = _audit_question(session, version=version, topic=topic, subtopic_ids=[sub.id])
    submit_review(
        session,
        question_id=false_alarm.id,
        decision=ReviewDecision.APPROVE,
        corrected_difficulty=Difficulty.EASY,
        corrected_subtopic_ids=[sub.id],
    )
    session.commit()

    report = build_judge_scorecard(session)
    difficulty = next(row for row in report.judges if row.metric is JudgeMetricId.DIFFICULTY)
    assert (difficulty.n, difficulty.agreements, difficulty.false_alarms, difficulty.flags) == (
        2,
        1,
        1,
        2,
    )
    stored = session.scalars(
        select(MemoryEpisodeRow).where(MemoryEpisodeRow.question_id == confirmed.id)
    ).first()
    assert stored is not None
    assert stored.source == SOURCE_AUDIT


def test_pending_audits_are_excluded_from_the_bank_until_approved(
    client: TestClient, session: Session
) -> None:
    version = CurriculumVersionRow(label="Bank")
    session.add(version)
    session.flush()
    topic = TopicRow(name="Loops", curriculum_version_id=version.id, position=0)
    session.add(topic)
    session.flush()
    sub = SubtopicRow(name="For", topic_id=topic.id, position=0)
    session.add(sub)
    session.commit()

    pending = _audit_question(session, version=version, topic=topic, subtopic_ids=[sub.id])
    ordinary = QuestionRepository(session).add(
        QuestionRow(
            prompt="Kept in the bank.",
            original_prompt="Kept in the bank.",
            status=QuestionStatus.VALIDATION_PASSED,
            curriculum_version_id=version.id,
        )
    )
    session.commit()

    listed = client.get("/api/questions").json()
    ids = {item["id"] for item in listed["questions"]}
    assert pending.id not in ids
    assert ordinary.id in ids
    assert listed["total"] == 1

    submit_review(
        session,
        question_id=pending.id,
        decision=ReviewDecision.APPROVE,
        corrected_difficulty=Difficulty.EASY,
        corrected_subtopic_ids=[sub.id],
    )
    session.commit()

    after = client.get("/api/questions").json()
    assert pending.id in {item["id"] for item in after["questions"]}
    assert after["total"] == 2
