"""Course-local styles (Task 18): create, scope to one course, use in setup, export to YAML."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.persistence.models import CourseRow
from app.styles import get_library, styles_for
from app.styles.checks import check_example, check_ids, check_lock, read_lock
from app.styles.loader import STYLES_DIR, dump_style, load_libraries, load_subject
from app.subjects import profile_for_course_id
from tests.conftest import TEST_PROFESSOR_ID

PYTHON = "intro_python"


@pytest.fixture
def http(configured_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(configured_app) as test_client:
        yield test_client


def _course(session: Session, name: str) -> int:
    course = CourseRow(name=name, subject=PYTHON, owner_id=TEST_PROFESSOR_ID)
    session.add(course)
    session.commit()
    return course.id


def _headers(course_id: int) -> dict[str, str]:
    return {"X-Course-Id": str(course_id)}


def _style_yaml(style_id: str = "py.my_output", **changes: Any) -> str:
    """A library style re-exported under a new id, optionally with fields changed."""
    (base,) = [s for s in get_library(PYTHON) if s.id == "py.predict_output"]
    data = yaml.safe_load(dump_style(base))
    data.update(id=style_id, name="Predict my output", **changes)
    return yaml.safe_dump(data, sort_keys=False)


def test_a_course_style_is_visible_only_in_its_course(http: TestClient, session: Session) -> None:
    mine, other = _course(session, "Mine"), _course(session, "Other")
    created = http.post("/api/styles", json={"yaml": _style_yaml()}, headers=_headers(mine))
    assert created.status_code == 201, created.text
    assert created.json()["subject"] == PYTHON

    listed = http.get("/api/styles", headers=_headers(mine)).json()
    assert [s["id"] for s in listed["styles"]][-1] == "py.my_output"
    assert listed["course_style_ids"] == ["py.my_output"]
    assert len(listed["styles"]) == len(get_library(PYTHON)) + 1

    elsewhere = http.get("/api/styles", headers=_headers(other)).json()
    assert "py.my_output" not in {s["id"] for s in elsewhere["styles"]}
    assert elsewhere["course_style_ids"] == []
    assert http.get("/api/styles/py.my_output/export", headers=_headers(other)).status_code == 404

    # Generation, the suggester and setup validation all read the same list.
    ids = {s.id for s in styles_for(session, profile_for_course_id(session, mine))}
    assert "py.my_output" in ids
    assert "py.my_output" not in {
        s.id for s in styles_for(session, profile_for_course_id(session, other))
    }


def test_the_exported_yaml_passes_the_library_checks(
    http: TestClient, session: Session, tmp_path: Path
) -> None:
    course = _course(session, "Mine")
    assert (
        http.post("/api/styles", json={"yaml": _style_yaml()}, headers=_headers(course)).status_code
        == 201
    )
    exported = http.get("/api/styles/py.my_output/export", headers=_headers(course))
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/yaml")
    assert 'filename="py.my_output.yaml"' in exported.headers["content-disposition"]

    # Drop it into a copy of the library, as the PR would, and run T17's checks.
    subject_dir = tmp_path / PYTHON
    subject_dir.mkdir()
    for path in (STYLES_DIR / PYTHON).iterdir():
        (subject_dir / path.name).write_bytes(path.read_bytes())
    (subject_dir / "py.my_output.yaml").write_text(exported.text, encoding="utf-8")
    styles = load_subject(subject_dir)
    (added,) = [s for s in styles if s.id == "py.my_output"]
    assert check_example(added, 0) == [] and check_example(added, 1) == []
    libraries = {**load_libraries(), PYTHON: styles}
    assert check_ids(libraries) == []
    assert (
        check_lock(libraries, [*read_lock(STYLES_DIR / "ids.lock"), f"{PYTHON}/py.my_output"]) == []
    )


def test_library_styles_export_too(http: TestClient, session: Session) -> None:
    exported = http.get(
        "/api/styles/py.trace_steps/export", headers=_headers(_course(session, "C"))
    )
    assert exported.status_code == 200
    assert "code: |-" in exported.text


@pytest.mark.parametrize(
    ("yaml_text", "message"),
    [
        (_style_yaml("py.predict_output"), "already exists"),
        (_style_yaml("zz.other_prefix"), "prefix"),
        (_style_yaml("Not An Id"), "<prefix>.<snake_case_name>"),
        (_style_yaml(question_type="essay"), "field 'question_type'"),
        ("just text", "expected a mapping"),
    ],
)
def test_a_bad_style_is_refused_with_the_reason(
    http: TestClient, session: Session, yaml_text: str, message: str
) -> None:
    response = http.post(
        "/api/styles", json={"yaml": yaml_text}, headers=_headers(_course(session, "C"))
    )
    assert response.status_code == 422, response.text
    assert message in response.text


def test_an_example_that_fails_its_type_checks_is_refused(
    http: TestClient, session: Session
) -> None:
    (base,) = [s for s in get_library(PYTHON) if s.id == "py.predict_output"]
    examples = [e.model_dump(exclude_defaults=True) for e in base.examples]
    examples[0]["answer"] = "not what it prints"
    response = http.post(
        "/api/styles",
        json={"yaml": _style_yaml(examples=examples)},
        headers=_headers(_course(session, "C")),
    )
    assert response.status_code == 422
    assert "py.my_output example 1: fails 'expected_output_verified'" in response.text


def test_a_round_prompt_states_a_course_style_in_an_owned_course(session: Session) -> None:
    """Regression: the lookup used the owner's personal key, which has no library, so a round
    spec in any owned preset course lost its style."""
    from test_styles import make_taxonomy

    from app.domain.enums import Difficulty, QuestionType
    from app.generation.base import BaseQuestionGenerator
    from app.generation.spec import QuestionSpec
    from app.styles import add_course_style

    course = CourseRow(name="Mine", subject=PYTHON, owner_id=TEST_PROFESSOR_ID)
    version, subtopics = make_taxonomy(session, course=course)
    profile = profile_for_course_id(session, course.id)
    add_course_style(session, profile, _style_yaml())
    generator = BaseQuestionGenerator(session=session)
    for style_id, name in (
        ("py.trace_steps", "Trace a loop"),
        ("py.my_output", "Predict my output"),
    ):
        spec = QuestionSpec(
            curriculum_version_id=version.id,
            question_type=QuestionType.OUTPUT_PREDICTION,
            difficulty=Difficulty.EASY,
            source_chunk_ids=["c1"],
            target_subtopic_id=subtopics[0].id,
            style_id=style_id,
        )
        block = generator._round_target(spec, version, None, generator.style_for(spec, version))
        assert f"Write it in this question style: {name}" in block
