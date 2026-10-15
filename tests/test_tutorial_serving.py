"""Tutorial blocks in a student's run (Phase 6, Task 27)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_tutorial_pregeneration import _block
from test_web_students import _enrol, _start

from app.coverage import create_question_set
from app.domain.enums import (
    CurriculumStatus,
    Difficulty,
    GuidanceLevel,
    QuestionStatus,
    QuestionType,
    TutorialBlockStatus,
)
from app.persistence.models import (
    CurriculumVersionRow,
    QuestionRow,
    QuestionSubtopicRow,
    SubtopicRow,
    TopicRow,
)

APPROVED = TutorialBlockStatus.APPROVED


def _course(session: Session, *, with_blocks: bool = True) -> tuple[int, int]:
    """One true/false question, approved tutorial blocks at every level, one frozen set.

    Returns the set id and the subtopic id."""
    version = CurriculumVersionRow(
        label="Intro", status=CurriculumStatus.APPROVED, approved_at=datetime.now(UTC)
    )
    topic = TopicRow(name="Lists", position=0, subtopics=[SubtopicRow(name="mutability")])
    version.topics.append(topic)
    session.add(version)
    session.flush()
    subtopic_id = topic.subtopics[0].id
    question = QuestionRow(
        prompt="Lists are mutable.",
        curriculum_version_id=version.id,
        topic_id=topic.id,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=Difficulty.EASY,
        status=QuestionStatus.APPROVED,
        content={"prompt": "Lists are mutable.", "correct_answer": True, "explanation": "Yes."},
        generator_name="base",
        generator_version="1",
    )
    session.add(question)
    session.flush()
    session.add(QuestionSubtopicRow(question_id=question.id, subtopic_id=subtopic_id))
    session.commit()
    if with_blocks:
        for recipe_id in ("py.misconception_line", "py.topic_flow"):
            for level in GuidanceLevel:
                _block(session, subtopic_id, recipe_id, status=APPROVED, level=level)
    frozen = create_question_set(session, label="Week 1", curriculum_version_id=version.id)
    return frozen.id, subtopic_id


def _run(client: TestClient, set_id: int) -> int:
    return _start(client, _enrol(client), set_id)


def test_a_low_prior_shows_pre_teaching_before_the_first_question(
    client: TestClient, session: Session
) -> None:
    set_id, _ = _course(session)
    served = client.get(f"/api/training-sessions/{_run(client, set_id)}/next").json()

    blocks = served["preteach_blocks"]
    assert blocks
    assert {b["guidance_level"] for b in blocks} == {"worked"}
    assert set(blocks[0]) == {"id", "recipe_id", "guidance_level", "renderer", "payload"}


def test_a_wrong_answer_gets_worked_blocks_from_the_frozen_set(
    client: TestClient, session: Session
) -> None:
    set_id, subtopic_id = _course(session)
    # Approved after the freeze: must never reach this run.
    late = _block(session, subtopic_id, "py.code_trace_stepper", status=APPROVED)
    served = client.get(f"/api/training-sessions/{_run(client, set_id)}/next").json()

    answered = client.post(f"/api/attempts/{served['attempt_id']}/answer", json={"answer": "false"})

    assert answered.status_code == 200, answered.text
    result = answered.json()
    assert result["score"] == 0
    blocks = result["tutorial_blocks"]
    assert 1 <= len(blocks) <= 4
    assert {b["guidance_level"] for b in blocks} == {"worked"}
    assert late.id not in {b["id"] for b in blocks}
    assert {b["recipe_id"] for b in blocks} == {"py.misconception_line", "py.topic_flow"}


def test_the_choice_is_the_same_on_a_reload(client: TestClient, session: Session) -> None:
    set_id, _ = _course(session)
    run_id = _run(client, set_id)
    first = client.get(f"/api/training-sessions/{run_id}/next").json()
    again = client.get(f"/api/training-sessions/{run_id}/next").json()
    assert again["resumed"] is True
    assert again["preteach_blocks"] == first["preteach_blocks"]


def test_a_set_without_blocks_falls_back_to_the_explanation(
    client: TestClient, session: Session
) -> None:
    set_id, _ = _course(session, with_blocks=False)
    served = client.get(f"/api/training-sessions/{_run(client, set_id)}/next").json()
    assert served["preteach_blocks"] == []

    result = client.post(
        f"/api/attempts/{served['attempt_id']}/answer", json={"answer": "false"}
    ).json()

    assert result["tutorial_blocks"] == []
    assert result["detail"]
