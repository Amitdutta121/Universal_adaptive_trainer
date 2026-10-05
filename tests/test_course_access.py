"""Per-course access (ADR-058): a professor reaches only the courses they own.

Runs against the real course-scope dependency, without the suite-wide override in
``conftest.py`` that lets a request without ``X-Course-Id`` stay unscoped. Two
professors each own one course; Bob, working inside his own course, asks for
Alice's rows by id and must get the same 404 as for a row that does not exist.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.backend import current_active_user
from app.config import Settings
from app.persistence.models import (
    BookRow,
    BookSectionRow,
    CourseRow,
    CurriculumVersionRow,
    QuestionRow,
    QuestionSetVersionRow,
    StudentRow,
    SubtopicRow,
    TopicRow,
    TrainingSessionRow,
    UserRow,
)
from app.web.routes.api.coverage import get_generation_client
from app.web.routes.api.retrieval import get_query_embedder


def _professor(email: str) -> UserRow:
    return UserRow(
        id=uuid.uuid4(),
        email=email,
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )


ALICE = _professor("alice@example.com")
BOB = _professor("bob@example.com")


@dataclass
class AliceCourse:
    course: int
    book: int
    version: int
    topic: int
    subtopic: int
    question: int
    student: int


@pytest.fixture
def as_user(settings: Settings) -> Iterator[dict[str, UserRow]]:
    """Who the app thinks is logged in; tests switch it by assigning ``["user"]``."""
    yield {"user": ALICE}


@pytest.fixture
def http(settings: Settings, as_user: dict[str, UserRow]) -> Iterator[TestClient]:
    from app.main import create_app

    app: FastAPI = create_app(settings)
    app.dependency_overrides[current_active_user] = lambda: as_user["user"]
    # Never called: a request naming another course's rows is refused first. Stubbed only
    # because building the real ones needs an LLM provider, which the suite never has.
    app.dependency_overrides[get_query_embedder] = object
    app.dependency_overrides[get_generation_client] = lambda: None
    with TestClient(app) as client:
        yield client


@pytest.fixture
def alice(http: TestClient, session: Session) -> AliceCourse:
    course = CourseRow(name="Alice's course", owner_id=ALICE.id)
    session.add(course)
    session.flush()
    book = BookRow(course_id=course.id, title="Alice's book", original_filename="a.json")
    subtopic = SubtopicRow(name="while loops", position=0)
    topic = TopicRow(name="Loops", subtopics=[subtopic])
    version = CurriculumVersionRow(label="Intro", course_id=course.id, topics=[topic])
    session.add_all([book, version])
    session.flush()
    question = QuestionRow(
        prompt="What does this loop print?",
        original_prompt="What does this loop print?",
        curriculum_version_id=version.id,
    )
    qset = QuestionSetVersionRow(label="Week 1", curriculum_version_id=version.id)
    student = StudentRow(display_name="Ada")
    session.add_all([question, qset, student])
    session.flush()
    session.add(TrainingSessionRow(student_id=student.id, set_version_id=qset.id))
    session.commit()
    return AliceCourse(
        course=course.id,
        book=book.id,
        version=version.id,
        topic=topic.id,
        subtopic=subtopic.id,
        question=question.id,
        student=student.id,
    )


@pytest.fixture
def bob_course(session: Session) -> int:
    course = CourseRow(name="Bob's course", owner_id=BOB.id)
    session.add(course)
    session.commit()
    return course.id


def _in(course: int) -> dict[str, str]:
    return {"X-Course-Id": str(course)}


def test_a_course_scoped_route_refuses_a_request_that_names_no_course(
    http: TestClient, alice: AliceCourse
) -> None:
    response = http.get("/api/books")

    assert response.status_code == 422
    assert "X-Course-Id" in response.json()["error"]["detail"]


def test_the_owner_reaches_their_course_and_its_rows(http: TestClient, alice: AliceCourse) -> None:
    headers = _in(alice.course)

    assert http.get(f"/api/courses/{alice.course}").status_code == 200
    assert http.get("/api/books", headers=headers).json()["total"] == 1
    assert http.get(f"/api/books/{alice.book}", headers=headers).status_code == 200
    assert (
        http.get(f"/api/curriculum/subtopics/{alice.subtopic}", headers=headers).status_code == 200
    )
    assert http.get(f"/api/questions/{alice.question}", headers=headers).status_code == 200
    assert http.get(f"/api/students/{alice.student}", headers=headers).status_code == 200
    assert http.get("/api/students", headers=headers).json()["total"] == 1


def test_another_professor_cannot_open_the_course(
    http: TestClient, as_user: dict[str, UserRow], alice: AliceCourse, bob_course: int
) -> None:
    as_user["user"] = BOB

    assert http.get(f"/api/courses/{alice.course}").status_code == 404
    assert http.patch(f"/api/courses/{alice.course}", json={"name": "Mine"}).status_code == 404
    # Naming the course in the header is refused just like an unknown course.
    assert http.get("/api/books", headers=_in(alice.course)).status_code == 404
    assert http.get("/api/questions", headers=_in(alice.course)).status_code == 404


def test_the_course_list_shows_only_the_professors_own_courses(
    http: TestClient, as_user: dict[str, UserRow], alice: AliceCourse, bob_course: int
) -> None:
    as_user["user"] = BOB

    listed = [course["id"] for course in http.get("/api/courses").json()["courses"]]
    overview = http.get("/api/courses/overview").json()

    assert listed == [bob_course]
    assert [entry["course"]["id"] for entry in overview["courses"]] == [bob_course]
    assert all(event["course_id"] == bob_course for event in overview["activity"])


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/books/{book}"),
        ("get", "/api/books/{book}/sections"),
        ("get", "/api/questions/generation-plan?book_id={book}"),
        ("get", "/api/curriculum/versions/{version}"),
        ("get", "/api/curriculum/subtopics/{subtopic}"),
        ("patch", "/api/curriculum/topics/{topic}"),
        ("patch", "/api/curriculum/subtopics/{subtopic}"),
        ("get", "/api/questions/{question}"),
        ("get", "/api/questions/{question}/evaluations"),
        ("post", "/api/questions/{question}/regenerate"),
        ("get", "/api/students/{student}"),
        ("get", "/api/students/{student}/progress"),
        ("get", "/api/training-sessions?student_id={student}"),
        ("get", "/api/students?curriculum_version_id={version}"),
    ],
)
def test_a_row_of_another_professors_course_is_not_found(
    http: TestClient,
    as_user: dict[str, UserRow],
    alice: AliceCourse,
    bob_course: int,
    method: str,
    path: str,
) -> None:
    as_user["user"] = BOB
    url = path.format(**vars(alice))
    body = (
        {"feedback": "Make it harder."}
        if url.endswith("/regenerate")
        else {"name": "Renamed"}
        if method == "patch"
        else None
    )

    response = http.request(method.upper(), url, headers=_in(bob_course), json=body)

    assert response.status_code == 404, response.text


def test_cohort_figures_leave_out_another_courses_students(
    http: TestClient, as_user: dict[str, UserRow], alice: AliceCourse, bob_course: int
) -> None:
    as_user["user"] = BOB

    roster = http.get("/api/students", headers=_in(bob_course)).json()
    summary = http.get("/api/students/class-summary", headers=_in(bob_course)).json()

    assert roster["total"] == 0
    assert summary["student_count"] == 0


# ---------------------------------------------------------------- ids in bodies and queries


@pytest.fixture
def alice_section(http: TestClient, session: Session, alice: AliceCourse) -> int:
    from app.domain.enums import StructureConfidence, StructureSource

    section = BookSectionRow(
        book_id=alice.book,
        title="While loops",
        text="A while loop repeats while its condition holds.",
        structure_source=next(iter(StructureSource)),
        structure_confidence=next(iter(StructureConfidence)),
    )
    session.add(section)
    session.commit()
    return section.id


@pytest.fixture
def alice_set(session: Session, alice: AliceCourse) -> int:
    return session.scalars(
        select(QuestionSetVersionRow.id).where(
            QuestionSetVersionRow.curriculum_version_id == alice.version
        )
    ).one()


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/coverage?set_version_id={set}", None),
        (
            "post",
            "/api/coverage/generation-runs",
            {"targets": [{"subtopic_id": "{subtopic}", "difficulty": "easy"}]},
        ),
        (
            "post",
            "/api/questions/generate",
            {
                "curriculum_version_id": "{version}",
                "question_type": "multiple_choice",
                "difficulty": "easy",
                "section_ids": ["{section}"],
            },
        ),
        (
            "post",
            "/api/questions/generate",
            {
                "question_type": "multiple_choice",
                "difficulty": "easy",
                "book_id": "{book}",
                "all_sections_of_book": True,
            },
        ),
        (
            "post",
            "/api/questions/generate-batch",
            {"chunks": [{"section_id": "{section}", "easy": 1}]},
        ),
        ("get", "/api/questions/generation-plan?book_id={book}&section_ids={section}", None),
        ("get", "/api/retrieval/sections?subtopic_id={subtopic}", None),
        ("get", "/api/setup?curriculum_version_id={version}", None),
        ("get", "/api/custom-judges?curriculum_version_id={version}", None),
        ("get", "/api/students/class-summary?curriculum_version_id={version}", None),
    ],
)
def test_another_courses_id_inside_a_body_or_query_is_not_found(
    http: TestClient,
    as_user: dict[str, UserRow],
    alice: AliceCourse,
    alice_section: int,
    alice_set: int,
    bob_course: int,
    method: str,
    path: str,
    body: dict | None,
) -> None:
    """Bob works inside his own course but names Alice's rows in the request itself."""
    ids = {**vars(alice), "section": alice_section, "set": alice_set}
    as_user["user"] = BOB

    def fill(value):
        if isinstance(value, str) and value.startswith("{"):
            return ids[value.strip("{}")]
        if isinstance(value, dict):
            return {key: fill(item) for key, item in value.items()}
        if isinstance(value, list):
            return [fill(item) for item in value]
        return value

    response = http.request(
        method.upper(), path.format(**ids), headers=_in(bob_course), json=fill(body)
    )

    assert response.status_code == 404, response.text


def test_a_review_cannot_correct_to_another_courses_subtopic(
    http: TestClient, session: Session, alice: AliceCourse
) -> None:
    other = CourseRow(name="Alice's other course", owner_id=ALICE.id)
    foreign = SubtopicRow(name="Elsewhere", position=0)
    session.add(other)
    session.flush()
    session.add(
        CurriculumVersionRow(
            label="Other", course_id=other.id, topics=[TopicRow(name="T", subtopics=[foreign])]
        )
    )
    session.commit()

    response = http.post(
        f"/api/questions/{alice.question}/review",
        headers=_in(alice.course),
        json={"decision": "approve", "corrected_subtopic_ids": [foreign.id]},
    )

    assert response.status_code == 404, response.text


def test_one_professors_judge_edit_does_not_reach_another_professor(
    http: TestClient, as_user: dict[str, UserRow], alice: AliceCourse, bob_course: int
) -> None:
    """Both courses are Intro Python; before ADR-059 they shared one judge panel."""
    saved = http.put(
        "/api/judge-prompts/issues",
        headers=_in(alice.course),
        json={"system_prompt": "ALICE'S OWN JUDGE"},
    )
    assert saved.status_code == 200, saved.text

    as_user["user"] = BOB
    bob = http.get("/api/judge-prompts", headers=_in(bob_course)).json()
    issues = next(prompt for prompt in bob["prompts"] if prompt["metric"] == "issues")

    assert issues["edited"] is False
    assert issues["system_prompt"] != "ALICE'S OWN JUDGE"

    as_user["user"] = ALICE
    alice_view = http.get("/api/judge-prompts", headers=_in(alice.course)).json()
    mine = next(prompt for prompt in alice_view["prompts"] if prompt["metric"] == "issues")
    assert mine["system_prompt"] == "ALICE'S OWN JUDGE"
