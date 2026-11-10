"""Setting a course up by chatting: the subject, and question styles drafted by the agent.

The LLM is faked; nothing reaches a provider.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic_ai import DeferredToolRequests
from sqlalchemy import func, select

from app.persistence.database import get_session_factory
from app.persistence.models import CourseRow, CourseStyleRow
from app.styles.library import get_library
from tests.agent_support import PROFESSOR_ID, result_of, run
from tests.test_tutorial_generator import QueuedClient

#: A multiple-choice style the fake model writes. The slug is messy on purpose: the id is built.
DRAFT: dict[str, Any] = {
    "slug": "Unit Check",
    "name": "Spot the right unit",
    "summary": "Students pick the SI unit of a quantity.",
    "question_type": "multiple_choice",
    "difficulty_range": ["easy"],
    "checked_by": "One correct option out of four",
    "applies_to": ["units"],
    "examples": [
        {
            "prompt": "What is the SI unit of force?",
            "options": [
                {"text": "newton", "correct": True},
                {"text": "joule"},
                {"text": "watt"},
                {"text": "pascal"},
            ],
            "answer": "newton",
            "grounding": "Forces",
        },
        {
            "prompt": "What is the SI unit of energy?",
            "options": [
                {"text": "newton"},
                {"text": "joule", "correct": True},
                {"text": "watt"},
                {"text": "pascal"},
            ],
            "answer": "joule",
            "grounding": "Energy",
        },
    ],
}


@pytest.fixture
def db(client: TestClient) -> Iterator[None]:
    """The app's schema, created by the client's lifespan; tools open their own sessions."""
    yield


def _course(subject: str = "intro_python", types: list[str] | None = None) -> int:
    with get_session_factory()() as session:
        course = CourseRow(
            name="Course",
            subject=subject,
            owner_id=PROFESSOR_ID,
            question_types=types or [],
        )
        session.add(course)
        session.commit()
        return course.id


def _course_row(course_id: int) -> CourseRow:
    with get_session_factory()() as session:
        row = session.get(CourseRow, course_id)
        session.expunge(row)
        return row


def _style_rows() -> int:
    with get_session_factory()() as session:
        return session.scalar(select(func.count()).select_from(CourseStyleRow))


# -- The subject -------------------------------------------------------------------------------


def test_a_course_created_by_name_only_can_take_its_subject_later(client: TestClient) -> None:
    course_id = client.post("/api/courses", json={"name": "Mechanics"}).json()["id"]

    changed = client.patch(f"/api/courses/{course_id}", json={"subject": "physics"})

    assert changed.status_code == 200, changed.text
    assert changed.json()["subject"] == "physics"
    # Without question_types the course takes the new subject's defaults.
    assert "coding" not in changed.json()["question_types"]
    assert client.patch(f"/api/courses/{course_id}", json={"subject": "nope"}).status_code == 422


def test_the_subject_is_fixed_once_the_course_has_a_style_of_its_own(client: TestClient) -> None:
    course_id = client.post("/api/courses", json={"name": "Python"}).json()["id"]
    style = get_library("intro_python")[0]
    with get_session_factory()() as session:
        session.add(
            CourseStyleRow(
                course_id=course_id,
                style_id="py.own",
                style=style.model_copy(update={"id": "py.own"}).model_dump(
                    mode="json", by_alias=True
                ),
            )
        )
        session.commit()

    refused = client.patch(f"/api/courses/{course_id}", json={"subject": "physics"})

    assert refused.status_code == 422, refused.text
    assert "subject can only change" in refused.text


def test_set_course_subject_sets_the_detected_subject_without_a_card(db) -> None:
    course_id = _course()
    call = ("set_course_subject", {"subject": "custom", "question_types": ["multiple_choice"]})

    result = run(call, course_id=course_id)

    assert not isinstance(result.output, DeferredToolRequests)
    settings = result_of(result.all_messages(), "set_course_subject")
    assert (settings.subject, settings.question_types, settings.changed) == (
        "custom",
        ["multiple_choice"],
        True,
    )
    assert _course_row(course_id).subject == "custom"


def test_setting_the_subject_the_course_already_has_changes_nothing(db) -> None:
    from app.assessment import catalog

    course_id = _course("intro_python", catalog.default_types_for("intro_python"))
    call = ("set_course_subject", {"subject": "intro_python"})

    settings = result_of(run(call, course_id=course_id).all_messages(), "set_course_subject")

    assert settings.changed is False
    assert settings.subject == "intro_python"


def test_subject_options_say_which_subjects_ship_styles(db) -> None:
    options = result_of(run(("subject_options", {})).all_messages(), "subject_options")
    by_id = {subject["id"]: subject for subject in options.subjects}
    assert by_id["intro_python"]["has_library"] is True
    assert by_id["custom"]["has_library"] is False
    assert {"id": "multiple_choice", "label": "Multiple choice"} in options.question_types


def test_course_overview_reports_the_subject_and_style_count(db) -> None:
    course_id = _course("custom", ["multiple_choice"])
    overview = result_of(
        run(("course_overview", {}), course_id=course_id).all_messages(), "course_overview"
    )
    assert (overview.subject, overview.question_types, overview.style_count) == (
        "custom",
        [{"id": "multiple_choice", "label": "Multiple choice"}],
        0,
    )
    assert overview.subject_name.startswith("Not set")


# -- Drafting a style --------------------------------------------------------------------------


def test_draft_style_writes_a_checked_style_for_a_course_without_a_library(db) -> None:
    course_id = _course("custom", ["multiple_choice", "true_false"])
    model = QueuedClient(DRAFT)

    drafted = result_of(
        run(
            ("draft_style", {"description": "quick unit checks"}),
            course_id=course_id,
            setup_client=model,
        ).all_messages(),
        "draft_style",
    )

    assert drafted.problems == []
    # A custom course owns its prefix; the slug is cleaned into the id.
    assert yaml.safe_load(drafted.yaml)["id"] == f"c{course_id}.unit_check"
    assert "quick unit checks" in model.calls[0]["prompt"]
    # The chat shows the draft as a card from these fields.
    assert drafted.style["name"] == "Spot the right unit"
    assert len(drafted.style["examples"]) == 2
    assert _style_rows() == 0

    saved = result_of(
        run(
            ("save_style", {"yaml": drafted.yaml}), decision=True, course_id=course_id
        ).all_messages(),
        "save_style",
    )
    assert saved.style_id == f"c{course_id}.unit_check"
    assert _style_rows() == 1


def test_a_draft_that_fails_the_style_checks_is_repaired_once(db) -> None:
    course_id = _course()
    two_correct = {**DRAFT, "examples": [DRAFT["examples"][0], DRAFT["examples"][0]]}
    two_correct["examples"] = [
        {**DRAFT["examples"][0], "options": [{"text": "a", "correct": True}] * 2},
        DRAFT["examples"][1],
    ]
    model = QueuedClient(two_correct, DRAFT)

    drafted = result_of(
        run(
            ("draft_style", {"description": "units"}), course_id=course_id, setup_client=model
        ).all_messages(),
        "draft_style",
    )

    assert drafted.problems == []
    # A Python course's own styles use the library's prefix.
    assert yaml.safe_load(drafted.yaml)["id"] == "py.unit_check"
    assert len(model.calls) == 2
    assert "cannot be used" in model.calls[1]["prompt"]


def test_a_draft_of_a_type_the_course_does_not_use_is_reported(db) -> None:
    course_id = _course("custom", ["true_false"])
    model = QueuedClient(DRAFT, DRAFT)

    drafted = result_of(
        run(
            ("draft_style", {"description": "units"}), course_id=course_id, setup_client=model
        ).all_messages(),
        "draft_style",
    )

    assert any("multiple_choice is not one of" in problem for problem in drafted.problems)


# -- Reading material --------------------------------------------------------------------------


def test_read_material_reads_a_book_in_order_and_in_parts(db) -> None:
    import book_documents as docs

    from app.agent import tools

    course_id = _course("custom", ["multiple_choice"])
    with get_session_factory()() as session:
        book = docs.chunked_book(session, docs.think_python(), course_id=course_id)
        session.commit()
        book_id = book.id

    first = result_of(
        run(("read_material", {"book_id": book_id}), course_id=course_id).all_messages(),
        "read_material",
    )
    assert first.total_chunks > 0
    assert first.text.startswith("## ")  # each section under its heading

    # A small limit forces parts: the next call starts where the last stopped.
    original = tools.MATERIAL_CHARS
    tools.MATERIAL_CHARS = 1
    try:
        part = result_of(
            run(("read_material", {"book_id": book_id}), course_id=course_id).all_messages(),
            "read_material",
        )
    finally:
        tools.MATERIAL_CHARS = original
    assert part.next_start == 1


def test_read_material_cannot_read_another_courses_book(db) -> None:
    import book_documents as docs

    mine, other = _course(), _course()
    with get_session_factory()() as session:
        book = docs.chunked_book(session, docs.think_python(), course_id=other)
        session.commit()
        book_id = book.id

    refusal = result_of(
        run(("read_material", {"book_id": book_id}), course_id=mine).all_messages(),
        "read_material",
    )
    assert refusal.error


def test_the_agent_is_told_not_to_assume_a_subject() -> None:
    from app.agent.agent import INSTRUCTIONS

    assert "Never assume a subject" in INSTRUCTIONS
    assert "read_material" in INSTRUCTIONS
