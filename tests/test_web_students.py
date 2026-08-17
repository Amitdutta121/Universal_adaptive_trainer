"""The student-facing API and pages (ADR-041).

The rule most easily broken here is that a served question must not carry its own
answer: the stored ``content`` holds ``correct_answer``, ``expected_output``,
``correct_option_index``, ``correct_order`` and ``reference_solution``, and any of
those reaching the page would make the whole measurement meaningless.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus, Difficulty, QuestionStatus, QuestionType
from app.persistence.models import (
    CurriculumVersionRow,
    QuestionRow,
    QuestionSubtopicRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import QuestionSetRepository


def _bank(session: Session, *, question_type: QuestionType = QuestionType.TRUE_FALSE) -> int:
    """An approved curriculum, one approved question, one frozen set. Returns the set id."""
    version = CurriculumVersionRow(
        label="Intro Python v1",
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    topic = TopicRow(curriculum_version_id=version.id, name="Loops", position=0)
    session.add(topic)
    session.flush()
    subtopic = SubtopicRow(topic_id=topic.id, name="for-loops", position=0)
    session.add(subtopic)
    session.flush()

    content: dict = {"prompt": "Lists are mutable.", "explanation": "Yes, they are."}
    if question_type is QuestionType.TRUE_FALSE:
        content["correct_answer"] = True
    elif question_type is QuestionType.MULTIPLE_CHOICE:
        content["options"] = ["tuple", "list", "dict"]
        content["correct_option_index"] = 1
    elif question_type is QuestionType.OUTPUT_PREDICTION:
        content["code"] = "print(41 + 1)"
        content["expected_output"] = "42"

    question = QuestionRow(
        prompt="Lists are mutable.",
        curriculum_version_id=version.id,
        topic_id=topic.id,
        question_type=question_type,
        difficulty=Difficulty.EASY,
        status=QuestionStatus.APPROVED,
        content=content,
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
    return frozen.id


def _enrol(client: TestClient, name: str = "Ada") -> int:
    response = client.post("/api/students", json={"display_name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _start(client: TestClient, student_id: int, set_id: int) -> int:
    response = client.post(
        "/api/training-sessions", json={"student_id": student_id, "set_version_id": set_id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestStudentsApi:
    def test_a_student_can_be_enrolled_and_listed(self, client: TestClient) -> None:
        student_id = _enrol(client)

        listing = client.get("/api/students")
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()["students"]] == [student_id]
        assert listing.json()["total"] == 1

    def test_a_duplicate_name_is_refused_with_a_reason(self, client: TestClient) -> None:
        _enrol(client, "Ada")
        response = client.post("/api/students", json={"display_name": "Ada"})
        assert response.status_code == 422
        assert "already exists" in response.json()["error"]["message"]

    def test_a_blank_name_is_refused(self, client: TestClient) -> None:
        assert client.post("/api/students", json={"display_name": "   "}).status_code == 422

    def test_the_dashboard_count_reflects_enrolment(self, client: TestClient) -> None:
        assert client.get("/api/counts").json()["students"] == 0
        _enrol(client)
        assert client.get("/api/counts").json()["students"] == 1

    def test_an_unknown_student_is_not_found(self, client: TestClient) -> None:
        assert client.get("/api/students/404/progress").status_code == 404


class TestTrainingApi:
    def test_the_full_loop_scores_and_moves_mastery(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        student_id = _enrol(client)
        run_id = _start(client, student_id, set_id)

        served = client.get(f"/api/training-sessions/{run_id}/next")
        assert served.status_code == 200, served.text
        body = served.json()
        assert body["ordinal"] == 1
        assert body["question_type"] == "true_false"
        assert body["resumed"] is False

        answered = client.post(
            f"/api/attempts/{body['attempt_id']}/answer", json={"answer": "true"}
        )
        assert answered.status_code == 200, answered.text
        result = answered.json()
        assert result["score"] == 100.0
        assert result["mastery_after"] > result["mastery_before"]

        progress = client.get(f"/api/students/{student_id}/progress").json()
        assert progress["answered"] == 1
        assert progress["average_score"] == 100.0
        assert progress["topics"][0]["p_known"] == result["mastery_after"]
        assert progress["subtopics"][0]["weakness"] < 1.0

    def test_asking_twice_returns_the_same_open_question(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        run_id = _start(client, _enrol(client), set_id)

        first = client.get(f"/api/training-sessions/{run_id}/next").json()
        second = client.get(f"/api/training-sessions/{run_id}/next").json()

        assert second["attempt_id"] == first["attempt_id"]
        assert second["resumed"] is True

    def test_answering_twice_is_refused(self, client: TestClient, session: Session) -> None:
        set_id = _bank(session)
        run_id = _start(client, _enrol(client), set_id)
        attempt_id = client.get(f"/api/training-sessions/{run_id}/next").json()["attempt_id"]

        client.post(f"/api/attempts/{attempt_id}/answer", json={"answer": "true"})
        again = client.post(f"/api/attempts/{attempt_id}/answer", json={"answer": "false"})
        assert again.status_code == 422
        assert "already been answered" in again.json()["error"]["message"]

    def test_a_set_with_nothing_approved_reports_a_conflict(
        self, client: TestClient, session: Session
    ) -> None:
        frozen = QuestionSetRepository(session).create(
            label="Empty", question_ids=[], curriculum_version_id=None
        )
        session.commit()
        run_id = _start(client, _enrol(client), frozen.id)

        response = client.get(f"/api/training-sessions/{run_id}/next")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "no_question_available"

    def test_an_ended_run_will_not_serve(self, client: TestClient, session: Session) -> None:
        set_id = _bank(session)
        run_id = _start(client, _enrol(client), set_id)
        assert client.post(f"/api/training-sessions/{run_id}/end").status_code == 200

        assert client.get(f"/api/training-sessions/{run_id}/next").status_code == 422


class TestTheAnswerIsNeverPublished:
    """A served question must not carry the answer, in any format."""

    def test_true_false_hides_the_correct_answer(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session, question_type=QuestionType.TRUE_FALSE)
        run_id = _start(client, _enrol(client), set_id)

        body = client.get(f"/api/training-sessions/{run_id}/next").json()
        assert "correct_answer" not in body
        assert "explanation" not in body
        assert "Yes, they are" not in str(body)

    def test_multiple_choice_publishes_options_but_not_the_index(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session, question_type=QuestionType.MULTIPLE_CHOICE)
        run_id = _start(client, _enrol(client), set_id)

        body = client.get(f"/api/training-sessions/{run_id}/next").json()
        assert body["options"] == ["tuple", "list", "dict"]
        assert "correct_option_index" not in body

    def test_output_prediction_publishes_code_but_not_the_output(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session, question_type=QuestionType.OUTPUT_PREDICTION)
        run_id = _start(client, _enrol(client), set_id)

        body = client.get(f"/api/training-sessions/{run_id}/next").json()
        assert body["code"] == "print(41 + 1)"
        assert "42" not in str(body["prompt"]) + str(body.get("options"))
        assert "expected_output" not in body

    def test_the_training_page_does_not_render_the_answer(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session, question_type=QuestionType.OUTPUT_PREDICTION)
        run_id = _start(client, _enrol(client), set_id)

        page = client.get(f"/training/{run_id}")
        assert page.status_code == 200
        assert "print(41 + 1)" in page.text
        assert "Yes, they are" not in page.text
        assert "expected_output" not in page.text


class TestStudentPages:
    def test_the_students_page_lists_and_offers_enrolment(self, client: TestClient) -> None:
        response = client.get("/students")
        assert response.status_code == 200
        assert "No students are enrolled yet." in response.text
        assert 'name="display_name"' in response.text

    def test_enrolling_through_the_page_redirects_back(self, client: TestClient) -> None:
        response = client.post("/students", data={"display_name": "Grace"}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/students"
        assert "Grace" in client.get("/students").text

    def test_a_duplicate_name_is_shown_as_a_banner(self, client: TestClient) -> None:
        client.post("/students", data={"display_name": "Grace"})
        response = client.post("/students", data={"display_name": "Grace"})
        assert response.status_code == 422
        assert "already exists" in response.text

    def test_the_progress_page_says_when_nothing_is_measured(self, client: TestClient) -> None:
        student_id = _enrol(client)
        response = client.get(f"/students/{student_id}")
        assert response.status_code == 200
        assert "Nothing measured yet." in response.text

    def test_starting_a_run_redirects_into_it(self, client: TestClient, session: Session) -> None:
        set_id = _bank(session)
        student_id = _enrol(client)

        response = client.post(
            f"/students/{student_id}/sessions",
            data={"set_version_id": set_id},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/training/")

    def test_the_training_page_shows_a_question_and_a_form(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        run_id = _start(client, _enrol(client), set_id)

        response = client.get(f"/training/{run_id}")
        assert response.status_code == 200
        assert "Lists are mutable." in response.text
        assert 'name="attempt_id"' in response.text
        assert 'value="true"' in response.text

    def test_submitting_an_answer_shows_the_score_and_the_explanation(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        run_id = _start(client, _enrol(client), set_id)
        attempt_id = client.get(f"/api/training-sessions/{run_id}/next").json()["attempt_id"]

        response = client.post(
            f"/training/{run_id}/answer",
            data={"attempt_id": attempt_id, "answer": "true"},
        )
        assert response.status_code == 200
        assert "100 / 100" in response.text
        assert "Yes, they are." in response.text
        assert "Next question" in response.text

    def test_a_wrong_answer_is_reported_as_incorrect(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        run_id = _start(client, _enrol(client), set_id)
        attempt_id = client.get(f"/api/training-sessions/{run_id}/next").json()["attempt_id"]

        response = client.post(
            f"/training/{run_id}/answer", data={"attempt_id": attempt_id, "answer": "false"}
        )
        assert response.status_code == 200
        assert "incorrect" in response.text
        assert "0 / 100" in response.text

    def test_resubmitting_shows_a_banner_rather_than_a_crash(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        run_id = _start(client, _enrol(client), set_id)
        attempt_id = client.get(f"/api/training-sessions/{run_id}/next").json()["attempt_id"]
        client.post(f"/training/{run_id}/answer", data={"attempt_id": attempt_id, "answer": "true"})

        again = client.post(
            f"/training/{run_id}/answer", data={"attempt_id": attempt_id, "answer": "true"}
        )
        assert again.status_code == 422
        assert "already been answered" in again.text

    def test_a_gap_in_the_set_is_explained_not_raised(
        self, client: TestClient, session: Session
    ) -> None:
        frozen = QuestionSetRepository(session).create(
            label="Empty", question_ids=[], curriculum_version_id=None
        )
        session.commit()
        run_id = _start(client, _enrol(client), frozen.id)

        response = client.get(f"/training/{run_id}")
        assert response.status_code == 200
        assert "Nothing to serve" in response.text
        assert "coverage grid" in response.text

    def test_ending_a_run_returns_to_the_progress_page(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        student_id = _enrol(client)
        run_id = _start(client, student_id, set_id)

        response = client.post(f"/training/{run_id}/end", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == f"/students/{student_id}"
