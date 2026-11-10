"""Question figures (ADR-080, fig1): the contract, file storage, the route, and what a student
is served."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domain.enums import (
    CurriculumStatus,
    Difficulty,
    QuestionStatus,
    QuestionType,
    TutorialRenderer,
)
from app.figures import figure_problems, parse_figure
from app.figures.storage import MAX_SVG_BYTES, FigureStorageError, read_svg, save_svg
from app.persistence.models import (
    CourseRow,
    CurriculumVersionRow,
    QuestionRow,
    QuestionSubtopicRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import QuestionSetRepository
from app.question_types import get_type, implemented_types
from app.tutorials.renderers import payload_problems
from app.web.routes.api.schemas import ServedQuestionOut
from app.web.routes.api.students import STUDENT_HEADER

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
    '<rect width="5" height="5"/></svg>'
)

DIAGRAM = {
    "kind": "diagram",
    "source": "flowchart TD\n  A --> B\n  A --> C",
    "alt": "A has two children, B and C.",
    "caption": "A tree.",
}
CHART = {
    "kind": "chart",
    "chart": {
        "type": "bar",
        "data": {"labels": ["a", "b"], "datasets": [{"label": "Count", "data": [3, 5]}]},
        "x_title": "Item",
        "y_title": "Count",
    },
    "alt": "Bars: a is 3, b is 5.",
    "caption": "",
}
SCATTER = {
    "kind": "chart",
    "chart": {
        "type": "scatter",
        "data": {"datasets": [{"label": "Runs", "data": [{"x": 1, "y": 2}, {"x": 2, "y": 4}]}]},
    },
    "alt": "Two points on a rising line.",
}
COMPUTED = {
    "kind": "computed",
    "file": f"3/{'a' * 64}.svg",
    "alt": "An 8 by 8 grid with walls.",
    "caption": "Dark cells are walls.",
}


# --- the schema -------------------------------------------------------------------------------


@pytest.mark.parametrize("figure", [DIAGRAM, CHART, SCATTER, COMPUTED])
def test_each_kind_parses_and_has_no_problems(figure: dict) -> None:
    assert parse_figure(figure).kind == figure["kind"]
    assert figure_problems(figure) == []


@pytest.mark.parametrize("alt", [None, "", "   "])
def test_a_figure_without_alt_text_is_refused(alt: str | None) -> None:
    figure = {key: value for key, value in DIAGRAM.items() if key != "alt"}
    if alt is not None:
        figure["alt"] = alt
    with pytest.raises(ValidationError):
        parse_figure(figure)
    assert figure_problems(figure)


def test_an_unknown_kind_or_extra_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        parse_figure({**DIAGRAM, "kind": "photo"})
    with pytest.raises(ValidationError):
        parse_figure({**CHART, "chart": {**CHART["chart"], "options": {"onClick": "x"}}})


@pytest.mark.parametrize(
    "source",
    [
        "A --> B",  # no diagram type
        "flowchart TD\n  A --> B\n  click A callback",
        "%%{init: {'securityLevel': 'loose'}}%%\nflowchart TD\n  A --> B",
        'flowchart TD\n  A["say \\"hi\\""] --> B',
        "flowchart TD\n  A[<script>x</script>] --> B",
    ],
)
def test_a_broken_mermaid_source_fails_figure_problems(source: str) -> None:
    assert figure_problems({**DIAGRAM, "source": source})


def test_tutorials_use_the_same_mermaid_check() -> None:
    bad = "flowchart TD\n  click A callback"
    assert payload_problems(TutorialRenderer.MERMAID, {"mermaid": bad}) == figure_problems(
        {**DIAGRAM, "source": bad}
    )
    assert payload_problems(TutorialRenderer.MERMAID, {"mermaid": DIAGRAM["source"]}) == []


def test_chart_data_must_fit_its_type() -> None:
    short = {
        **CHART,
        "chart": {
            "type": "bar",
            "data": {"labels": ["a", "b", "c"], "datasets": [{"label": "n", "data": [1]}]},
        },
    }
    assert figure_problems(short)
    numbers_on_scatter = {
        **SCATTER,
        "chart": {"type": "scatter", "data": {"datasets": [{"label": "n", "data": [1, 2]}]}},
    }
    assert figure_problems(numbers_on_scatter)
    points_on_bar = {
        **CHART,
        "chart": {
            "type": "bar",
            "data": {"labels": ["a"], "datasets": [{"label": "n", "data": [{"x": 1, "y": 2}]}]},
        },
    }
    assert figure_problems(points_on_bar)


@pytest.mark.parametrize("file", ["../secrets.svg", "3/abc.svg", f"3/{'a' * 64}.png", "/etc/x"])
def test_a_computed_figure_must_point_at_a_storage_key(file: str) -> None:
    assert figure_problems({**COMPUTED, "file": file})


# --- storage ----------------------------------------------------------------------------------


def test_an_svg_round_trips_through_storage(settings) -> None:
    key = save_svg(7, SVG)
    assert key.startswith("7/") and key.endswith(".svg")
    assert read_svg(key) == SVG.encode()
    assert (settings.figure_dir / key).is_file()
    assert save_svg(7, SVG) == key  # content-addressed: stored once
    assert figure_problems({**COMPUTED, "file": key}) == []


@pytest.mark.parametrize(
    "key", ["../x.svg", "7/../../x.svg", f"7/../{'a' * 64}.svg", "7\\x.svg", "C:/x.svg", ""]
)
def test_storage_refuses_keys_outside_its_folder(settings, key: str) -> None:
    with pytest.raises(FigureStorageError):
        read_svg(key)


def test_storage_refuses_oversized_or_non_svg_content(settings) -> None:
    with pytest.raises(FigureStorageError):
        save_svg(7, "<svg>" + "x" * MAX_SVG_BYTES + "</svg>")
    with pytest.raises(FigureStorageError):
        save_svg(7, "<html><script>alert(1)</script></html>")
    assert save_svg(7, '<?xml version="1.0"?>\n' + SVG)


# --- the route --------------------------------------------------------------------------------


def test_the_figure_route_serves_the_svg_as_an_inert_image(client: TestClient) -> None:
    key = save_svg(3, SVG)
    response = client.get(f"/api/figures/{key}")
    assert response.status_code == 200
    assert response.content == SVG.encode()
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; style-src 'unsafe-inline'"
    )


def test_the_figure_route_is_public_like_the_student_flow(settings) -> None:
    from app.main import create_app

    key = save_svg(3, SVG)
    with TestClient(create_app(settings)) as anonymous:
        assert anonymous.get(f"/api/figures/{key}").status_code == 200


def test_the_figure_route_404s_for_unknown_or_malformed_keys(client: TestClient) -> None:
    assert client.get(f"/api/figures/3/{'b' * 64}.svg").status_code == 404
    assert client.get("/api/figures/3/notahash.svg").status_code == 404
    assert client.get("/api/figures/3/..%2F..%2Fsecret.svg").status_code == 404


# --- what a student sees ----------------------------------------------------------------------

#: Every type's content with its answer fields, so a leak would show.
_ANSWERS: dict[QuestionType, dict] = {
    QuestionType.MULTIPLE_CHOICE: {"options": ["x", "y"], "correct_option_index": 1},
    QuestionType.TRUE_FALSE: {"correct_answer": True},
    QuestionType.OUTPUT_PREDICTION: {"code": "print(1)", "expected_output": "SECRET_OUTPUT"},
    QuestionType.CODE_COMPLETION: {"code": "def f(): ...", "reference_solution": "SECRET_SOL"},
    QuestionType.DEBUGGING: {"code": "def f(): ...", "reference_solution": "SECRET_SOL"},
    QuestionType.CODING: {"reference_solution": "SECRET_SOL"},
    QuestionType.PARSONS: {
        "blocks": [{"id": "a", "text": "x = 1", "indent": 0}],
        "correct_order": ["a"],
    },
    QuestionType.NUMERIC_RESPONSE: {"value": 424242.0, "unit": "m", "calculation": "424242"},
    QuestionType.EQUATION_RESPONSE: {"expression": "SECRET_EXPR", "variables": ["x"]},
}
_FIGURE_FIELDS = {"kind", "alt", "caption", "source", "chart", "file"}


@pytest.mark.parametrize("question_type", implemented_types())
@pytest.mark.parametrize("figure", [DIAGRAM, CHART, COMPUTED])
def test_every_type_passes_the_figure_and_nothing_else(
    question_type: QuestionType, figure: dict
) -> None:
    content = {
        "prompt": "Read the figure.",
        "explanation": "SECRET_EXPLANATION",
        "figure": figure,
        **_ANSWERS[question_type],
    }
    view = get_type(question_type).student_view(content, seed=1)
    assert view.figure is not None
    assert set(view.figure) <= _FIGURE_FIELDS
    assert view.figure == parse_figure(figure).model_dump(mode="json")

    published = _served(question_type, content).model_dump_json()
    for secret in ("SECRET", "424242", "correct_", "expected_output", "explanation"):
        assert secret not in published


def test_a_figure_with_smuggled_fields_or_problems_is_not_served() -> None:
    view = get_type(QuestionType.TRUE_FALSE).student_view
    assert view({"figure": {**DIAGRAM, "answer": True}}, seed=1).figure is None
    assert view({"figure": {**DIAGRAM, "source": "A --> B"}}, seed=1).figure is None
    assert view({"figure": "not a figure"}, seed=1).figure is None
    assert view({}, seed=1).figure is None


def test_numeric_says_whether_the_answer_takes_a_unit() -> None:
    view = get_type(QuestionType.NUMERIC_RESPONSE).student_view
    assert view({"value": 3, "unit": "m/s"}, seed=1).takes_unit is True
    assert view({"value": 3, "unit": ""}, seed=1).takes_unit is False
    assert view({"value": 3, "unit": "dimensionless"}, seed=1).takes_unit is False
    assert view({"value": 3, "accepted_units": ["km"]}, seed=1).takes_unit is True
    assert _served(QuestionType.NUMERIC_RESPONSE, {"value": 3}).takes_unit is False
    assert _served(QuestionType.TRUE_FALSE, {"correct_answer": True}).takes_unit is None


def _served(question_type: QuestionType, content: dict) -> ServedQuestionOut:
    attempt = SimpleNamespace(
        id=5,
        session_id=2,
        ordinal=1,
        requested_difficulty=Difficulty.EASY,
        served_difficulty=Difficulty.EASY,
        subtopic_id=1,
    )
    question = SimpleNamespace(
        id=9, question_type=question_type, prompt="Read the figure.", content=content
    )
    served = SimpleNamespace(attempt=attempt, question=question, resumed=False, fallback_used=False)
    return ServedQuestionOut.from_served(served)


# --- end to end through the API ---------------------------------------------------------------


def _bank_with_figure(
    session: Session, figure: dict, *, course_id: int | None = None
) -> tuple[int, int]:
    """One approved true/false question carrying ``figure``, in a frozen set."""
    version = CurriculumVersionRow(
        label="v1",
        course_id=course_id,
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    topic = TopicRow(curriculum_version_id=version.id, name="Topic", position=0)
    session.add(topic)
    session.flush()
    subtopic = SubtopicRow(topic_id=topic.id, name="Subtopic", position=0)
    session.add(subtopic)
    session.flush()
    question = QuestionRow(
        prompt="The path from S to G takes 22 moves.",
        curriculum_version_id=version.id,
        topic_id=topic.id,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=Difficulty.EASY,
        status=QuestionStatus.APPROVED,
        content={
            "prompt": "The path from S to G takes 22 moves.",
            "correct_answer": True,
            "explanation": "Counted on the grid.",
            "figure": figure,
        },
        generator_name="base",
        generator_version="1",
    )
    session.add(question)
    session.flush()
    session.add(QuestionSubtopicRow(question_id=question.id, subtopic_id=subtopic.id))
    frozen = QuestionSetRepository(session).create(
        label="Week 1", question_ids=[question.id], curriculum_version_id=version.id
    )
    session.commit()
    return frozen.id, question.id


def test_a_student_is_served_the_figure_and_it_shows_in_review(
    client: TestClient, session: Session
) -> None:
    figure = {**COMPUTED, "file": save_svg(1, SVG)}
    set_id, question_id = _bank_with_figure(session, figure)

    enrolled = client.post(
        "/api/students", json={"display_name": "Ada", "email": "ada@example.edu"}
    ).json()
    client.headers[STUDENT_HEADER] = enrolled["resume_token"]
    run = client.post(
        "/api/training-sessions", json={"student_id": enrolled["id"], "set_version_id": set_id}
    )
    assert run.status_code == 201, run.text
    served = client.get(f"/api/training-sessions/{run.json()['id']}/next").json()

    assert served["figure"] == parse_figure(figure).model_dump(mode="json")
    assert client.get(f"/api/figures/{served['figure']['file']}").content == SVG.encode()

    answered = client.post(f"/api/attempts/{served['attempt_id']}/answer", json={"answer": "true"})
    assert answered.json()["score"] == 100  # grading ignores the figure
    review = client.get(f"/api/attempts/{served['attempt_id']}/review").json()
    assert review["question"]["figure"]["file"] == figure["file"]

    professor = client.get(f"/api/questions/{question_id}").json()
    assert professor["question"]["figure"]["kind"] == "computed"


def test_the_seed_script_adds_figure_questions_once(session: Session) -> None:
    from scripts.seed_figure_questions import seed

    course = CourseRow(name="Course")
    session.add(course)
    session.flush()
    _bank_with_figure(session, DIAGRAM, course_id=course.id)

    added, set_id = seed(session, course.id)
    session.commit()

    assert len(added) == 6 and set_id is not None
    rows = [session.get(QuestionRow, question_id) for question_id in added]
    assert {row.question_type for row in rows} == {
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.NUMERIC_RESPONSE,
        QuestionType.TRUE_FALSE,
    }
    assert {row.content["figure"]["kind"] for row in rows} == {"diagram", "chart", "computed"}
    for row in rows:
        assert figure_problems(row.content["figure"]) == []
        assert get_type(row.question_type).student_view(row.content, seed=1).figure is not None
    computed = next(row for row in rows if row.content["figure"]["kind"] == "computed")
    assert read_svg(computed.content["figure"]["file"]).lstrip().startswith(b"<")

    assert seed(session, course.id) == ([], None)
