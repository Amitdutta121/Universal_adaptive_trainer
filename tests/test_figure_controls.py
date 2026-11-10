"""fig6: professor controls for figures (ADR-080).

A figure edit in review is stored as an edit, checked and judged again; a course can turn
figures off for new questions. Regenerating one computed copy is in ``test_computed_figures``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from llm_fakes import MetricJudgeClient, judged
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session
from test_figure_styles import DIAGRAM, figure_course, figure_style, round_spec

from app.domain.enums import (
    Difficulty,
    EvaluationTrigger,
    JudgeMetricId,
    QuestionStatus,
    QuestionType,
    ReviewDecision,
)
from app.errors import DomainRuleError
from app.feedback import rejudge_edited_figure, route_review_outcome, submit_review
from app.generation import GenerationService
from app.generation.base import BaseQuestionGenerator
from app.generation.schemas import MultipleChoiceDraft, response_model_for
from app.persistence.database import _alembic_config
from app.persistence.models import (
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    QuestionSubtopicRow,
    ReviewOutcomeRow,
)
from app.styles import QuestionStyle

STEM = "Which stage comes right after Stage A in the figure?"
EDITED = {**DIAGRAM, "source": 'flowchart LR\n  A["Stage A"] --> C["Stage C"]'}
CHART = {
    "kind": "chart",
    "alt": "Units per year.",
    "caption": "",
    "chart": {
        "type": "bar",
        "data": {"labels": ["2019", "2020"], "datasets": [{"label": "Units", "data": [4, 9]}]},
    },
}


@pytest.fixture(autouse=True)
def four_metric_panel(monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings

    monkeypatch.setenv("JUDGE_METRICS_ENABLED", "issues,subtopic,difficulty,generatability")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> list[QuestionStyle]:
    import app.styles.library

    styles: list[QuestionStyle] = []
    monkeypatch.setattr(app.styles.library, "get_library", lambda subject: list(styles))
    return styles


@pytest.fixture
def env(session: Session) -> SimpleNamespace:
    return figure_course(
        session, subject="custom", name="Course", question_types=["multiple_choice"]
    )


def _question(session: Session, env: SimpleNamespace, figure: dict[str, Any]) -> QuestionRow:
    row = QuestionRow(
        curriculum_version_id=env.version.id,
        topic_id=env.topic.id,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=Difficulty.MEDIUM,
        status=QuestionStatus.VALIDATION_PASSED,
        prompt=STEM,
        reference_solution="Stage B",
        tests="",
        content={
            "options": ["Stage B", "Stage C", "Stage A", "None"],
            "correct_option_index": 0,
            "figure": figure,
        },
        generator_name="test-gen",
        generator_version="1",
    )
    session.add(row)
    session.flush()
    session.add(QuestionSubtopicRow(question_id=row.id, subtopic_id=env.subtopic.id))
    # The judges rejected it, so a professor keeping it is a disagreement on record.
    row.pedagogical_eval = judged(question_id=row.id, failing={JudgeMetricId.ISSUES}).model_dump(
        mode="json"
    )
    session.commit()
    return row


def _edit(session: Session, row: QuestionRow, figure: dict[str, Any] | None, **fields: Any):
    return submit_review(
        session,
        question_id=row.id,
        decision=ReviewDecision.EDIT,
        prompt=fields.get("prompt", row.prompt),
        reference_solution=row.reference_solution,
        tests=row.tests,
        figure=figure,
    )


def _judge(env: SimpleNamespace) -> MetricJudgeClient:
    return MetricJudgeClient(
        topic_id=env.topic.id, subtopic_ids=[env.subtopic.id], difficulty=Difficulty.MEDIUM
    )


def _edit_evaluations(session: Session, row: QuestionRow) -> list[QuestionEvaluationRow]:
    return list(
        session.scalars(
            select(QuestionEvaluationRow).where(
                QuestionEvaluationRow.question_id == row.id,
                QuestionEvaluationRow.trigger == EvaluationTrigger.PROFESSOR_EDIT,
            )
        )
    )


# --- AC1: a figure edit is stored as an edit, re-validated and re-judged ----------------------


def test_a_diagram_edit_is_stored_as_an_edit_and_keeps_the_generated_figure(
    session: Session, env: SimpleNamespace
) -> None:
    row = _question(session, env, DIAGRAM)

    review = _edit(session, row, EDITED)
    session.commit()

    assert review.changed_fields == ["figure"]
    assert review.edited_figure == EDITED
    assert row.content["figure"] == EDITED and row.original_figure == DIAGRAM
    assert row.status is QuestionStatus.APPROVED
    # A second edit keeps the generated figure, not the first edit.
    _edit(session, row, {**EDITED, "caption": "Two stages"})
    assert row.original_figure == DIAGRAM


def test_a_chart_edit_is_stored_too(session: Session, env: SimpleNamespace) -> None:
    row = _question(session, env, CHART)
    edited = {**CHART, "chart": {**CHART["chart"], "type": "line"}}

    review = _edit(session, row, edited)

    assert review.changed_fields == ["figure"]
    assert row.content["figure"]["chart"]["type"] == "line"


UNLABELLED = {
    **CHART,
    "chart": {**CHART["chart"], "data": {**CHART["chart"]["data"], "labels": []}},
}


@pytest.mark.parametrize(
    ("start", "figure", "message"),
    [
        (DIAGRAM, {**DIAGRAM, "source": "flowchart LR\n  click A x"}, "cannot be shown"),
        (DIAGRAM, {**DIAGRAM, "alt": ""}, "cannot be shown"),
        (CHART, UNLABELLED, "cannot be shown"),
        (DIAGRAM, CHART, "keeps its kind"),
    ],
)
def test_an_edited_figure_that_cannot_be_drawn_is_refused_with_why(
    session: Session,
    env: SimpleNamespace,
    start: dict[str, Any],
    figure: dict[str, Any],
    message: str,
) -> None:
    row = _question(session, env, start)

    with pytest.raises(DomainRuleError, match=message) as raised:
        _edit(session, row, figure)

    assert raised.value.detail
    session.rollback()
    assert session.scalar(select(ProfessorReviewRow.id)) is None


def test_the_same_figure_is_not_a_change(session: Session, env: SimpleNamespace) -> None:
    row = _question(session, env, DIAGRAM)

    with pytest.raises(DomainRuleError, match="at least one changed field"):
        _edit(session, row, dict(DIAGRAM))


def test_a_figure_edit_is_judged_again_after_its_outcome_is_recorded(
    session: Session, env: SimpleNamespace
) -> None:
    row = _question(session, env, DIAGRAM)
    review = _edit(session, row, EDITED)
    outcome = route_review_outcome(session, review)
    assert outcome is not None
    judge_label = outcome.row.judge

    assert rejudge_edited_figure(session, review, client=_judge(env)) is True
    session.commit()

    (evaluation,) = _edit_evaluations(session, row)
    assert evaluation.gate == "approved"
    assert row.pedagogical_eval["gate"] == "approved"
    # The outcome keeps the verdict the professor reviewed.
    stored = session.scalar(select(ReviewOutcomeRow).where(ReviewOutcomeRow.review_id == review.id))
    assert stored.judge == judge_label


def test_a_prompt_only_edit_is_not_judged_again(session: Session, env: SimpleNamespace) -> None:
    row = _question(session, env, DIAGRAM)
    client = _judge(env)
    review = _edit(session, row, None, prompt="Which stage follows Stage A?")

    assert rejudge_edited_figure(session, review, client=client) is False
    assert client.calls == 0 and _edit_evaluations(session, row) == []


def test_the_review_route_takes_a_figure_and_skips_the_judge_without_a_model(
    client: TestClient, session: Session, env: SimpleNamespace
) -> None:
    row = _question(session, env, DIAGRAM)
    body = {
        "decision": "edit",
        "prompt": STEM,
        "reference_solution": "Stage B",
        "tests": "",
        "figure": EDITED,
    }

    bad = client.post(
        f"/api/questions/{row.id}/review",
        json={**body, "figure": {**EDITED, "source": "pie\n  click A x"}},
    )
    assert bad.status_code == 422, bad.text
    assert "click" in bad.text

    response = client.post(f"/api/questions/{row.id}/review", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["changed_fields"] == ["figure"]
    detail = client.get(f"/api/questions/{row.id}").json()
    assert detail["content"]["figure"] == EDITED and detail["original_figure"] == DIAGRAM
    with Session(session.get_bind()) as fresh:
        assert _edit_evaluations(fresh, fresh.get(QuestionRow, row.id)) == []


def test_the_review_route_judges_a_figure_edit_with_a_model(
    client: TestClient, session: Session, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.evaluation.service

    fake = _judge(env)
    monkeypatch.setattr(app.evaluation.service, "get_structured_client", lambda **_: fake)
    row = _question(session, env, DIAGRAM)

    response = client.post(
        f"/api/questions/{row.id}/review",
        json={
            "decision": "edit",
            "prompt": STEM,
            "reference_solution": "Stage B",
            "tests": "",
            "figure": EDITED,
        },
    )

    assert response.status_code == 201, response.text
    assert fake.calls == 4
    with Session(session.get_bind()) as fresh:
        (evaluation,) = _edit_evaluations(fresh, fresh.get(QuestionRow, row.id))
        assert evaluation.gate == "approved"


# --- AC3: a course can turn figures off --------------------------------------------------------


def test_a_course_with_figures_off_generates_its_figure_styles_as_text(
    session: Session, env: SimpleNamespace, library: list[QuestionStyle]
) -> None:
    style = figure_style(
        f"c{env.course.id}.read_diagram",
        "diagram",
        subject=env.profile.storage_key,
        example_figure=DIAGRAM,
    )
    library.append(style)
    env.course.figures_enabled = False
    session.commit()

    prepared = BaseQuestionGenerator(session=session).prepare(
        round_spec(session, env, style), version=env.version
    )

    assert prepared.style is not None and prepared.style.figure == "none"
    assert all(example.figure is None for example in prepared.style.examples)
    assert response_model_for(QuestionType.MULTIPLE_CHOICE, prepared.style) is MultipleChoiceDraft
    assert "Mermaid" not in prepared.prompt


def test_a_computed_style_is_written_as_a_plain_question_when_figures_are_off(
    session: Session, env: SimpleNamespace, library: list[QuestionStyle]
) -> None:
    style = figure_style(f"c{env.course.id}.drawn", "computed", subject=env.profile.storage_key)
    library.append(style)
    env.course.figures_enabled = False
    session.commit()
    draft = MultipleChoiceDraft(
        topic_id=env.topic.id,
        subtopic_ids=[env.subtopic.id],
        prompt="Which stage comes after Stage A?",
        options=["Stage B", "Stage C", "Stage A", "None of them"],
        correct_option_index=0,
        explanation="The material moves A, B, C.",
    )

    row = GenerationService(
        session, client=MetricJudgeClient(draft=draft, difficulty=Difficulty.MEDIUM)
    ).generate_round_question(round_spec(session, env, style), version=env.version, round_id=None)

    assert row is not None
    assert "figure" not in row.content and row.figure_program is None


def test_the_course_settings_turn_figures_off_and_on(client: TestClient) -> None:
    created = client.post("/api/courses", json={"name": "Figures"})
    assert created.status_code == 201, created.text
    course = created.json()
    assert course["figures_enabled"] is True

    off = client.patch(f"/api/courses/{course['id']}", json={"figures_enabled": False})
    assert off.status_code == 200, off.text
    assert off.json()["figures_enabled"] is False
    assert client.get(f"/api/courses/{course['id']}").json()["figures_enabled"] is False
    renamed = client.patch(f"/api/courses/{course['id']}", json={"name": "Renamed"})
    assert renamed.json()["figures_enabled"] is False


# --- the migration -----------------------------------------------------------------------------


def test_the_figure_controls_migration_downgrades_and_upgrades_cleanly(engine: Engine) -> None:
    def columns(connection, table: str) -> set[str]:
        return {c["name"] for c in inspect(connection).get_columns(table)}

    with engine.begin() as connection:
        config = _alembic_config(connection)
        command.downgrade(config, "0034_question_variants")
        assert "figures_enabled" not in columns(connection, "courses")
        assert "original_figure_json" not in columns(connection, "questions")
        assert "edited_figure_json" not in columns(connection, "professor_reviews")
        command.upgrade(config, "head")
        assert "figures_enabled" in columns(connection, "courses")
        assert "original_figure_json" in columns(connection, "questions")
        assert "edited_figure_json" in columns(connection, "professor_reviews")
