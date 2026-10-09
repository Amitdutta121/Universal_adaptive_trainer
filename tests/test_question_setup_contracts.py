"""Phase 0 contracts of docs/QUESTION_SETUP_PLAN.md.

The migration adds the setup tables and columns to an existing database, the new rows round-trip
through their repositories, and every stub endpoint is registered and answers 501 until Phase 1
implements it. Replace the 501 assertions as each endpoint lands.
"""

from __future__ import annotations

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

from app.domain.enums import CustomJudgeKind, Difficulty, ReviewDecision, RoundStatus
from app.persistence.database import _alembic_config, init_db
from app.persistence.models import (
    CurriculumVersionRow,
    CustomJudgeRow,
    GenerationRoundRow,
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    QuestionSetupRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import (
    CustomJudgeRepository,
    GenerationRoundRepository,
    QuestionSetupRepository,
)
from app.styles import QuestionStyle

NEW_TABLES = {"question_setups", "generation_rounds", "custom_judges"}
NEW_COLUMNS = {
    "questions": {"style_id", "round_id", "target_subtopic_id"},
    "professor_reviews": {"corrected_difficulty", "corrected_subtopic_ids_json"},
    "question_evaluations": {"custom_results_json"},
}


def _columns(engine: Engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _assert_schema(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) >= NEW_TABLES
    for table, columns in NEW_COLUMNS.items():
        assert columns <= _columns(engine, table), table


def test_a_fresh_database_has_the_setup_schema(engine: Engine) -> None:
    _assert_schema(engine)


def test_a_0004_database_is_upgraded_keeping_its_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        command.downgrade(_alembic_config(connection), "0004_subject_scoped_personalization")
        connection.execute(
            text(
                "INSERT INTO questions (kind, difficulty, status, prompt, generator_kind, "
                "generator_name, generator_version, priority, times_used, created_at) VALUES "
                "('discrete', 'easy', 'generated', 'Old question', 'base', 'g', '1', 0, 0, "
                "'2026-01-01')"
            )
        )
    assert not NEW_TABLES & set(inspect(engine).get_table_names())
    assert "style_id" not in _columns(engine, "questions")

    init_db(engine)

    _assert_schema(engine)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        row = connection.execute(text("SELECT prompt, style_id, round_id FROM questions")).one()
    assert version == "0020_judge_snapshots"
    assert tuple(row) == ("Old question", None, None)


def test_setup_rows_round_trip(session: Session) -> None:
    version = CurriculumVersionRow(label="v1")
    topic = TopicRow(name="Loops", subtopics=[SubtopicRow(name="for loops")])
    version.topics.append(topic)
    session.add(version)
    session.flush()
    subtopic_id = topic.subtopics[0].id

    setups = QuestionSetupRepository(session)
    assert setups.current(version.id) is None
    setup = setups.add(
        QuestionSetupRow(
            curriculum_version_id=version.id,
            approved_styles={str(subtopic_id): ["py.trace_output"]},
            cell_targets=[{"subtopic_id": subtopic_id, "difficulty": "easy", "target": 3}],
        )
    )

    rounds = GenerationRoundRepository(session)
    assert rounds.next_number(setup.id) == 1
    first = rounds.add(GenerationRoundRow(setup_id=setup.id, number=1, requested=10))
    assert first.status is RoundStatus.QUEUED
    rounds.update(first.id, status=RoundStatus.RUNNING, produced=2)

    question = QuestionRow(
        prompt="What does this print?",
        curriculum_version_id=version.id,
        style_id="py.trace_output",
        round_id=first.id,
        target_subtopic_id=subtopic_id,
    )
    session.add(question)
    session.flush()
    session.add(
        ProfessorReviewRow(
            question_id=question.id,
            decision=ReviewDecision.APPROVE,
            corrected_difficulty=Difficulty.MEDIUM,
            corrected_subtopic_ids=[subtopic_id],
        )
    )
    session.add(
        QuestionEvaluationRow(
            question_id=question.id,
            run_id="r1",
            custom_results=[{"judge_id": 1, "passed": True}],
        )
    )
    judges = CustomJudgeRepository(session)
    judge = judges.add(
        CustomJudgeRow(curriculum_version_id=version.id, rule_text="No global variables")
    )
    judges.update(judge.id, enabled=False)
    session.commit()
    session.expire_all()

    assert setups.current(version.id).approved_styles == {str(subtopic_id): ["py.trace_output"]}
    loaded_round = rounds.get(first.id)
    assert (loaded_round.status, loaded_round.produced) == (RoundStatus.RUNNING, 2)
    assert rounds.next_number(setup.id) == 2
    loaded = session.get(QuestionRow, question.id)
    assert (loaded.style_id, loaded.round_id, loaded.target_subtopic_id) == (
        "py.trace_output",
        first.id,
        subtopic_id,
    )
    review = loaded.reviews[0]
    assert review.corrected_difficulty is Difficulty.MEDIUM
    assert review.corrected_subtopic_ids == [subtopic_id]
    assert loaded.evaluations[0].custom_results == [{"judge_id": 1, "passed": True}]
    assert judges.list_for_version(version.id, enabled_only=True) == []
    assert judges.get(judge.id).kind is CustomJudgeKind.LLM


def test_a_style_needs_two_examples_and_a_difficulty() -> None:
    example = {"prompt": "x = 1; print(x)", "answer": "1"}
    style = QuestionStyle(
        id="py.trace_output",
        subject="intro_python",
        name="Predict what the code prints",
        summary="Read a short program and write its output.",
        question_type="output_prediction",
        difficulty_range=["easy", "medium"],
        checked_by="Runs the code and compares the output",
        examples=(example, example),
    )
    assert style.difficulty_range == [Difficulty.EASY, Difficulty.MEDIUM]
    with pytest.raises(ValueError):
        QuestionStyle.model_validate({**style.model_dump(), "difficulty_range": []})
    with pytest.raises(ValueError):
        QuestionStyle.model_validate({**style.model_dump(), "examples": [example]})


# The setup routes (agent A) are implemented: tests/test_setup_routes.py.
IMPLEMENTED_ROUTES = [
    ("POST", "/api/rounds", {"setup_id": 1}),
    ("GET", "/api/rounds/1", None),
    ("GET", "/api/custom-judges?curriculum_version_id=1", None),
    ("POST", "/api/custom-judges", {"curriculum_version_id": 1, "rule_text": "No globals"}),
    ("PATCH", "/api/custom-judges/1", {"enabled": False}),
]


@pytest.mark.parametrize(("method", "path", "body"), IMPLEMENTED_ROUTES)
def test_setup_routes_are_registered_and_validate_missing_resources(
    client: TestClient, method: str, path: str, body: dict | None
) -> None:
    response = client.request(method, path, json=body)
    assert response.status_code == 404, response.text


def test_review_request_rejects_an_empty_subtopic_correction(client: TestClient) -> None:
    response = client.post(
        "/api/questions/1/review",
        json={"decision": "approve", "corrected_subtopic_ids": []},
    )
    assert response.status_code == 422
