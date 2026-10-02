"""Courses: the picker's API, and that a course's screens show only its own content."""

from __future__ import annotations

import book_documents as docs
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import QuestionStatus
from app.persistence.models import QuestionRow

TAXONOMY = (
    b'{"schema_version":"1","label":"%s","topics":['
    b'{"name":"Loops","subtopics":[{"name":"While loops"},{"name":"For loops"}]}]}'
)


def _course(client: TestClient, name: str) -> int:
    response = client.post("/api/courses", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _in(course_id: int) -> dict[str, str]:
    return {"X-Course-Id": str(course_id)}


def _import_book(client: TestClient, course_id: int, title: str) -> dict:
    response = client.post(
        "/api/books",
        headers=_in(course_id),
        data={"title": title},
        files={"file": ("book.json", docs.to_bytes(docs.think_python()), "application/json")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _import_taxonomy(client: TestClient, course_id: int, label: str) -> dict:
    response = client.post(
        "/api/curriculum/versions",
        headers=_in(course_id),
        files={"file": ("taxonomy.json", TAXONOMY % label.encode(), "application/json")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_created_course_is_listed_with_empty_counts(client: TestClient) -> None:
    assert client.get("/api/courses").json() == {"courses": []}

    course_id = _course(client, "  CS 135  ")

    (course,) = client.get("/api/courses").json()["courses"]
    assert course["id"] == course_id
    assert course["name"] == "CS 135"
    assert (course["book_count"], course["curriculum_version_count"], course["question_count"]) == (
        0,
        0,
        0,
    )


def test_a_blank_course_name_is_rejected(client: TestClient) -> None:
    assert client.post("/api/courses", json={"name": "   "}).status_code == 422


def test_a_course_can_be_renamed(client: TestClient) -> None:
    course_id = _course(client, "Draft")
    response = client.patch(f"/api/courses/{course_id}", json={"name": "CS 202"})
    assert response.status_code == 200
    assert client.get(f"/api/courses/{course_id}").json()["name"] == "CS 202"


def test_an_unknown_course_header_is_a_404(client: TestClient) -> None:
    response = client.get("/api/books", headers=_in(999))
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Course 999 does not exist."


def test_each_course_sees_only_its_own_books_and_taxonomies(
    client: TestClient, session: Session
) -> None:
    python = _course(client, "Python")
    stats = _course(client, "Statistics")
    python_book = _import_book(client, python, "Think Python")
    stats_book = _import_book(client, stats, "OpenIntro Statistics")
    python_tax = _import_taxonomy(client, python, "Python taxonomy")
    stats_tax = _import_taxonomy(client, stats, "Stats taxonomy")

    books = client.get("/api/books", headers=_in(python)).json()
    assert [book["title"] for book in books["books"]] == ["Think Python"]
    assert books["total"] == 1

    versions = client.get("/api/curriculum/versions", headers=_in(stats)).json()
    assert [version["label"] for version in versions["versions"]] == ["Stats taxonomy"]
    # Each course has its own active taxonomy: importing Stats' did not displace Python's.
    assert versions["approved_version_id"] == stats_tax["version"]["id"]
    approved = client.get("/api/curriculum/approved", headers=_in(python)).json()
    assert approved["version"]["id"] == python_tax["version"]["id"]

    # A row from another course is not reachable from this one by id either.
    assert client.get(f"/api/books/{stats_book['id']}", headers=_in(python)).status_code == 404
    assert (
        client.get(
            f"/api/curriculum/versions/{python_tax['version']['id']}", headers=_in(stats)
        ).status_code
        == 404
    )
    assert client.get(f"/api/books/{python_book['id']}", headers=_in(python)).status_code == 200

    # Questions follow their curriculum version into its course.
    session.add_all(
        [
            QuestionRow(
                prompt="python q",
                original_prompt="python q",
                curriculum_version_id=python_tax["version"]["id"],
                status=QuestionStatus.VALIDATION_PASSED,
            ),
            QuestionRow(
                prompt="stats q",
                original_prompt="stats q",
                curriculum_version_id=stats_tax["version"]["id"],
                status=QuestionStatus.VALIDATION_PASSED,
            ),
        ]
    )
    session.commit()
    listing = client.get("/api/questions", headers=_in(stats)).json()
    assert [question["prompt"] for question in listing["questions"]] == ["stats q"]
    assert listing["total"] == 1
    queue = client.get("/api/questions/review-queue", headers=_in(python)).json()
    assert queue["total"] == 1
    assert queue["question"]["question"]["prompt"] == "python q"

    counts = client.get("/api/counts", headers=_in(python)).json()
    assert (counts["books"], counts["curriculum_versions"], counts["questions"]) == (1, 1, 1)

    listed = {course["name"]: course for course in client.get("/api/courses").json()["courses"]}
    assert listed["Statistics"]["book_count"] == 1
    assert listed["Statistics"]["question_count"] == 1


def test_without_the_header_nothing_is_hidden(client: TestClient) -> None:
    """Scripts and callers outside the Studio keep the whole-installation view."""
    _import_book(client, _course(client, "A"), "Book A")
    _import_book(client, _course(client, "B"), "Book B")
    assert client.get("/api/books").json()["total"] == 2


def test_the_overview_reports_progress_and_activity_per_course(client: TestClient) -> None:
    course_id = _course(client, "Python")
    empty_id = _course(client, "Empty")
    _import_book(client, course_id, "Think Python")
    _import_taxonomy(client, course_id, "Python taxonomy")

    overview = client.get("/api/courses/overview").json()
    cards = {card["course"]["name"]: card for card in overview["courses"]}

    python = cards["Python"]
    assert python["owned_by_you"] is True
    assert python["course"]["book_count"] == 1
    assert {step["key"]: step["done"] for step in python["setup"]} == {
        "materials": True,
        "taxonomy": True,
        "coverage": False,
        "review": False,
        "question_set": False,
        "classes": False,
    }
    # A taxonomy with no approved questions is measurable coverage: zero.
    assert python["coverage"] == 0.0
    # Nobody has answered anything, so there is nothing to average or rank.
    assert python["avg_mastery"] is None
    assert python["most_missed"] is None

    empty = cards["Empty"]
    assert empty["coverage"] is None
    assert not any(step["done"] for step in empty["setup"])
    assert empty["course"]["id"] == empty_id

    kinds = [(event["kind"], event["course_name"]) for event in overview["activity"]]
    assert ("book", "Python") in kinds
    assert ("taxonomy", "Python") in kinds


def test_every_taxonomy_has_its_own_classroom_link(client: TestClient, session: Session) -> None:
    course_id = _course(client, "Python")
    older = _import_taxonomy(client, course_id, "Older taxonomy")["version"]["id"]
    newer = _import_taxonomy(client, course_id, "Newer taxonomy")["version"]["id"]
    session.add_all(
        [
            QuestionRow(
                prompt=f"q{version}",
                original_prompt=f"q{version}",
                curriculum_version_id=version,
                status=QuestionStatus.APPROVED,
            )
            for version in (older, newer)
        ]
    )
    session.commit()

    # No link until the professor creates one.
    assert client.get(f"/api/question-sets/taxonomy/{older}").status_code == 404

    # A link for a taxonomy that is not the selected one: the point of the change.
    created = client.post(f"/api/question-sets/taxonomy/{older}/sync", headers=_in(course_id))
    assert created.status_code == 201, created.text
    assert created.json()["curriculum_version_id"] == older
    client.post(f"/api/question-sets/taxonomy/{newer}/sync", headers=_in(course_id))

    # The public join page resolves each taxonomy to its own snapshot, without logging in.
    older_set = client.get(f"/api/question-sets/taxonomy/{older}").json()
    newer_set = client.get(f"/api/question-sets/taxonomy/{newer}").json()
    assert older_set["curriculum_version_id"] == older
    assert newer_set["curriculum_version_id"] == newer
    assert older_set["id"] != newer_set["id"]

    # Updating a link moves it to a new snapshot; the old one is kept (ADR-036).
    again = client.post(f"/api/question-sets/taxonomy/{older}/sync", headers=_in(course_id)).json()
    assert (
        client.get(f"/api/question-sets/taxonomy/{older}").json()["id"]
        == again["id"]
        != older_set["id"]
    )

    # One call lists every taxonomy with the snapshot its link serves.
    links = {
        row["curriculum_version_id"]: row
        for row in client.get("/api/question-sets/taxonomy-links", headers=_in(course_id)).json()[
            "links"
        ]
    }
    assert set(links) == {older, newer}
    assert links[older]["classroom"]["id"] == again["id"]
    assert links[newer]["approved_question_count"] == 1

    # Another course cannot touch this course's taxonomy.
    other = _course(client, "Other")
    assert (
        client.post(f"/api/question-sets/taxonomy/{older}/sync", headers=_in(other)).status_code
        == 404
    )


def test_the_review_queue_follows_the_chosen_taxonomy(client: TestClient, session: Session) -> None:
    course_id = _course(client, "Python")
    first = _import_taxonomy(client, course_id, "First")["version"]["id"]
    second = _import_taxonomy(client, course_id, "Second")["version"]["id"]
    session.add_all(
        [
            QuestionRow(
                prompt=f"q{version}",
                original_prompt=f"q{version}",
                curriculum_version_id=version,
                status=QuestionStatus.VALIDATION_PASSED,
            )
            for version in (first, second, second)
        ]
    )
    session.commit()
    queue = client.get(
        "/api/questions/review-queue",
        headers=_in(course_id),
        params={"curriculum_version_id": first},
    ).json()
    assert queue["total"] == 1
    assert queue["question"]["question"]["prompt"] == f"q{first}"


def test_the_catalog_lists_subjects_and_only_built_types_are_offerable(client: TestClient) -> None:
    body = client.get("/api/courses/catalog").json()
    types = {item["id"]: item for item in body["question_types"]}
    assert types["coding"]["offerable"] is True
    assert types["coding"]["also_needs"] == ["code.python.execute"]
    assert types["numeric_response"]["offerable"] is True
    assert types["equation_response"]["offerable"] is True
    # Listed so a professor sees what is coming, but not pickable yet.
    assert types["short_explanation"]["offerable"] is False
    assert types["short_explanation"]["ai_graded"] is True
    subjects = {item["id"]: item for item in body["subjects"]}
    assert subjects["physics"]["default_types"] == [
        "multiple_choice",
        "true_false",
        "numeric_response",
        "equation_response",
    ]
    assert subjects["physics"]["coming_soon_types"] == []
    # Examples are in the subject's own terms, not Python's.
    assert "elastic collision" in subjects["physics"]["examples"]["multiple_choice"]


def test_a_course_stores_its_question_types_and_derives_capabilities(client: TestClient) -> None:
    created = client.post(
        "/api/courses",
        json={"name": "Physics 101", "subject": "physics", "question_types": ["multiple_choice"]},
    )
    assert created.status_code == 201, created.text
    course = created.json()
    assert course["subject"] == "physics"
    assert course["question_types"] == ["multiple_choice"]
    assert course["capabilities"] == ["structured.choice"]

    coding = client.post(
        "/api/courses",
        json={"name": "CS 1", "subject": "intro_python", "question_types": ["coding"]},
    ).json()
    # Ticking a code type turns on what grades it and what it needs; the professor never picks.
    assert coding["capabilities"] == ["code.python.execute", "code.python.tests"]

    # A course created by name only keeps the legacy behaviour: all seven Python types.
    legacy = client.post("/api/courses", json={"name": "Old style"}).json()
    assert legacy["subject"] == "intro_python"
    assert len(legacy["question_types"]) == 7


def test_a_type_that_is_not_built_cannot_be_chosen(client: TestClient) -> None:
    refused = client.post(
        "/api/courses",
        json={"name": "Physics", "subject": "physics", "question_types": ["short_explanation"]},
    )
    assert refused.status_code == 422
    assert "short_explanation" in refused.json()["error"]["detail"]
    assert client.post("/api/courses", json={"name": "X", "question_types": []}).status_code == 422
    assert client.post("/api/courses", json={"name": "X", "subject": "nope"}).status_code == 422


def test_generation_refuses_a_type_the_course_did_not_choose(client: TestClient) -> None:
    course_id = client.post(
        "/api/courses",
        json={"name": "Physics", "subject": "physics", "question_types": ["multiple_choice"]},
    ).json()["id"]
    response = client.post(
        "/api/questions/generate",
        headers=_in(course_id),
        json={"section_ids": [1], "question_type": "coding", "difficulty": "easy"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["message"] == "This course does not use these question types."
    assert "Coding" in response.json()["error"]["detail"]

    batch = client.post(
        "/api/questions/generate-batch",
        headers=_in(course_id),
        json={"chunks": [{"section_id": 1, "easy": 1, "question_types": ["parsons"]}]},
    )
    assert batch.status_code == 422, batch.text
