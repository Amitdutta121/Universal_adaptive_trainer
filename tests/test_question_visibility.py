"""Hiding approved questions when a style or type is turned off (ADR-070, task-139).

Guards: counts per style, type and subtopic cell; hide and show scoped to the course or one
subtopic; a hidden question is never served to a student; a hidden question is not a reject
for ``style_rejects`` and does not fill a round's cell.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adaptive.inventory import StudentBank
from app.domain.enums import CurriculumStatus, Difficulty, QuestionStatus, QuestionType
from app.generation import rounds
from app.persistence.models import (
    CurriculumVersionRow,
    QuestionRow,
    QuestionSubtopicRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import QuestionSetRepository
from app.web.routes.api.deps import COURSE_HEADER


class Bank:
    def __init__(self, course: int, version: int, topic: int, loops: int, strings: int) -> None:
        self.course = course
        self.version = version
        self.topic = topic
        self.loops = loops
        self.strings = strings


def _taxonomy(session: Session, course_id: int) -> Bank:
    version = CurriculumVersionRow(
        course_id=course_id,
        label="Python v1",
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    topic = TopicRow(curriculum_version_id=version.id, name="Basics", position=0)
    session.add(topic)
    session.flush()
    loops = SubtopicRow(topic_id=topic.id, name="Loops", position=0)
    strings = SubtopicRow(topic_id=topic.id, name="Strings", position=1)
    session.add_all([loops, strings])
    session.commit()
    return Bank(course_id, version.id, topic.id, loops.id, strings.id)


def _question(
    session: Session,
    bank: Bank,
    *,
    subtopic_id: int,
    style_id: str | None = "py.trace",
    question_type: QuestionType = QuestionType.OUTPUT_PREDICTION,
    difficulty: Difficulty = Difficulty.EASY,
    status: QuestionStatus = QuestionStatus.APPROVED,
) -> QuestionRow:
    row = QuestionRow(
        prompt="What does this print?",
        curriculum_version_id=bank.version,
        topic_id=bank.topic,
        question_type=question_type,
        difficulty=difficulty,
        status=status,
        style_id=style_id,
        target_subtopic_id=subtopic_id,
        generator_name="round",
        generator_version="1",
    )
    session.add(row)
    session.flush()
    session.add(QuestionSubtopicRow(question_id=row.id, subtopic_id=subtopic_id))
    session.commit()
    return row


@pytest.fixture
def bank(client: TestClient, session: Session) -> Bank:
    course = client.post("/api/courses", json={"name": "Visibility"}).json()["id"]
    bank = _taxonomy(session, course)
    _question(session, bank, subtopic_id=bank.loops)
    _question(session, bank, subtopic_id=bank.loops, difficulty=Difficulty.MEDIUM)
    _question(session, bank, subtopic_id=bank.strings)
    _question(
        session,
        bank,
        subtopic_id=bank.strings,
        style_id="py.fill",
        question_type=QuestionType.CODE_COMPLETION,
    )
    # Not approved: never counted, never hidden.
    _question(session, bank, subtopic_id=bank.loops, status=QuestionStatus.GENERATED)
    _question(session, bank, subtopic_id=bank.loops, status=QuestionStatus.REJECTED)
    return bank


def _counts(client: TestClient, bank: Bank) -> dict:
    response = client.get(
        "/api/question-visibility",
        params={"curriculum_version_id": bank.version},
        headers={COURSE_HEADER: str(bank.course)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _set(client: TestClient, bank: Bank, **body: object) -> int:
    response = client.post(
        "/api/question-visibility", json=body, headers={COURSE_HEADER: str(bank.course)}
    )
    assert response.status_code == 200, response.text
    return response.json()["changed"]


def _style(counts: dict, style_id: str) -> tuple[int, int]:
    entry = next(e for e in counts["by_style"] if e["style_id"] == style_id)
    return entry["approved"], entry["hidden"]


def _cell(counts: dict, subtopic_id: int, style_id: str, difficulty: str) -> tuple[int, int]:
    entry = next(
        e
        for e in counts["by_cell"]
        if (e["subtopic_id"], e["style_id"], e["difficulty"]) == (subtopic_id, style_id, difficulty)
    )
    return entry["approved"], entry["hidden"]


def test_counts_are_per_style_type_and_subtopic_cell(client: TestClient, bank: Bank) -> None:
    counts = _counts(client, bank)
    assert _style(counts, "py.trace") == (3, 0)
    assert _style(counts, "py.fill") == (1, 0)
    by_type = {e["question_type"]: (e["approved"], e["hidden"]) for e in counts["by_type"]}
    assert by_type == {"output_prediction": (3, 0), "code_completion": (1, 0)}
    assert _cell(counts, bank.loops, "py.trace", "easy") == (1, 0)
    assert _cell(counts, bank.loops, "py.trace", "medium") == (1, 0)
    assert _cell(counts, bank.strings, "py.trace", "easy") == (1, 0)


def test_hiding_a_style_course_wide_then_showing_it_again(client: TestClient, bank: Bank) -> None:
    assert _set(client, bank, hidden=True, style_ids=["py.trace"]) == 3
    counts = _counts(client, bank)
    assert _style(counts, "py.trace") == (0, 3)
    assert _style(counts, "py.fill") == (1, 0)

    assert _set(client, bank, hidden=False, style_ids=["py.trace"]) == 3
    assert _style(_counts(client, bank), "py.trace") == (3, 0)


def test_hiding_in_one_subtopic_leaves_the_others(client: TestClient, bank: Bank) -> None:
    assert _set(client, bank, hidden=True, style_ids=["py.trace"], subtopic_id=bank.loops) == 2
    counts = _counts(client, bank)
    assert _style(counts, "py.trace") == (1, 2)
    assert _cell(counts, bank.loops, "py.trace", "easy") == (0, 1)
    assert _cell(counts, bank.strings, "py.trace", "easy") == (1, 0)


def test_hiding_a_question_type(client: TestClient, bank: Bank, session: Session) -> None:
    assert _set(client, bank, hidden=True, question_types=["code_completion"]) == 1
    counts = _counts(client, bank)
    by_type = {e["question_type"]: (e["approved"], e["hidden"]) for e in counts["by_type"]}
    assert by_type == {"output_prediction": (3, 0), "code_completion": (0, 1)}
    hidden = session.query(QuestionRow).filter(QuestionRow.status == QuestionStatus.HIDDEN)
    assert [row.style_id for row in hidden] == ["py.fill"]


def test_hide_names_styles_or_types_not_both(client: TestClient, bank: Bank) -> None:
    response = client.post(
        "/api/question-visibility",
        json={"hidden": True, "style_ids": ["py.trace"], "question_types": ["coding"]},
        headers={COURSE_HEADER: str(bank.course)},
    )
    assert response.status_code == 422


def test_another_courses_questions_are_not_touched(
    client: TestClient, bank: Bank, session: Session
) -> None:
    other_course = client.post("/api/courses", json={"name": "Other"}).json()["id"]
    other = _taxonomy(session, other_course)
    _question(session, other, subtopic_id=other.loops)
    assert _set(client, bank, hidden=True, style_ids=["py.trace"]) == 3
    assert _style(_counts(client, other), "py.trace") == (1, 0)


def test_a_hidden_question_is_not_served(client: TestClient, bank: Bank, session: Session) -> None:
    sets = QuestionSetRepository(session)
    frozen = sets.create(
        label="Frozen",
        question_ids=sets.approved_question_ids(curriculum_version_id=bank.version),
        curriculum_version_id=bank.version,
    )
    session.commit()
    before = sets.candidates_for_cell(frozen.id, subtopic_id=bank.loops, difficulty=Difficulty.EASY)
    assert len(before) == 1

    _set(client, bank, hidden=True, style_ids=["py.trace"], subtopic_id=bank.loops)
    session.expire_all()
    after = sets.candidates_for_cell(frozen.id, subtopic_id=bank.loops, difficulty=Difficulty.EASY)
    assert after == []
    assert bank.loops not in sets.servable_subtopic_ids(frozen.id)
    served = {row.style_id for row in StudentBank(session).questions(frozen.id)}
    assert served == {"py.trace", "py.fill"}  # the Strings questions are still served
    assert all(
        row.status is QuestionStatus.APPROVED for row in StudentBank(session).questions(frozen.id)
    )
    # A new set never picks a hidden question up.
    assert len(sets.approved_question_ids(curriculum_version_id=bank.version)) == 2


def test_a_hidden_question_is_not_a_reject_and_does_not_fill_a_cell(
    client: TestClient, bank: Bank, session: Session
) -> None:
    rejects_before = rounds.style_rejects(session, bank.version)
    assert rejects_before == {((bank.loops, Difficulty.EASY), "py.trace"): 1}

    _set(client, bank, hidden=True, style_ids=["py.trace"])
    session.expire_all()
    assert rounds.style_rejects(session, bank.version) == rejects_before
    # The pending GENERATED question still counts; the two hidden ones no longer do.
    assert rounds.cell_counts(session, bank.version)[(bank.loops, Difficulty.EASY)] == 1
    assert (bank.loops, Difficulty.MEDIUM) not in rounds.cell_counts(session, bank.version)
