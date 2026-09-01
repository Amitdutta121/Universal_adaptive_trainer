"""The student-facing API (ADR-041).

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
    elif question_type is QuestionType.PARSONS:
        content["blocks"] = [
            {"id": "head", "text": "for value in items:", "indent": 0},
            {"id": "body", "text": "print(value)", "indent": 1},
        ]
        content["correct_order"] = ["head", "body"]

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


def _enrol_payload(name: str) -> dict[str, str]:
    slug = name.strip().lower().replace(" ", ".") or "learner"
    return {"display_name": name, "email": f"{slug}@example.edu"}


def _enrol(client: TestClient, name: str = "Ada") -> int:
    response = client.post("/api/students", json=_enrol_payload(name))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _enrol_with_token(client: TestClient, name: str = "Ada") -> tuple[int, str]:
    response = client.post("/api/students", json=_enrol_payload(name))
    assert response.status_code == 201, response.text
    body = response.json()
    return body["id"], body["resume_token"]


def _start(client: TestClient, student_id: int, set_id: int) -> int:
    response = client.post(
        "/api/training-sessions", json={"student_id": student_id, "set_version_id": set_id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestStudentsApi:
    def test_the_current_prod_classroom_is_public(self, settings, session: Session) -> None:
        set_id = _bank(session)
        QuestionSetRepository(session).point_alias("prod", set_version_id=set_id)
        session.commit()

        from app.main import create_app

        with TestClient(create_app(settings)) as public_client:
            response = public_client.get("/api/question-sets/prod")

        assert response.status_code == 200
        assert response.json()["id"] == set_id
        assert response.json()["is_prod"] is True

    def test_a_student_can_be_enrolled_and_listed(self, client: TestClient) -> None:
        student_id = _enrol(client)

        listing = client.get("/api/students")
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()["students"]] == [student_id]
        assert listing.json()["total"] == 1

    def test_a_duplicate_name_is_refused_with_a_reason(self, client: TestClient) -> None:
        _enrol(client, "Ada")
        response = client.post("/api/students", json=_enrol_payload("Ada"))
        assert response.status_code == 422
        assert "already exists" in response.json()["error"]["message"]

    def test_a_blank_name_is_refused(self, client: TestClient) -> None:
        payload = _enrol_payload("Ada") | {"display_name": "   "}
        assert client.post("/api/students", json=payload).status_code == 422

    def test_an_email_is_required(self, client: TestClient) -> None:
        assert client.post("/api/students", json={"display_name": "Ada"}).status_code == 422

    def test_a_malformed_email_is_refused(self, client: TestClient) -> None:
        payload = {"display_name": "Ada", "email": "ada-at-example"}
        assert client.post("/api/students", json=payload).status_code == 422

    def test_the_roster_and_enrolment_carry_the_email(self, client: TestClient) -> None:
        created = client.post("/api/students", json=_enrol_payload("Ada")).json()
        assert created["email"] == "ada@example.edu"
        row = client.get("/api/students").json()["students"][0]
        assert row["email"] == "ada@example.edu"

    def test_the_dashboard_count_reflects_enrolment(self, client: TestClient) -> None:
        assert client.get("/api/counts").json()["students"] == 0
        _enrol(client)
        assert client.get("/api/counts").json()["students"] == 1

    def test_an_unknown_student_is_not_found(self, client: TestClient) -> None:
        assert client.get("/api/students/404/progress").status_code == 404

    def test_enrolment_hands_back_a_resume_token(self, client: TestClient) -> None:
        body = client.post("/api/students", json=_enrol_payload("Ada")).json()
        assert body["resume_token"]
        assert isinstance(body["resume_token"], str)

    def test_the_professor_roster_never_carries_a_resume_token(self, client: TestClient) -> None:
        _enrol(client)
        row = client.get("/api/students").json()["students"][0]
        assert "resume_token" not in row


def _answer_one(client: TestClient, set_id: int, name: str) -> int:
    """Enrol ``name``, run one true/false question, answer it correctly."""
    student_id = _enrol(client, name)
    run_id = _start(client, student_id, set_id)
    attempt_id = client.get(f"/api/training-sessions/{run_id}/next").json()["attempt_id"]
    client.post(f"/api/attempts/{attempt_id}/answer", json={"answer": "true"})
    return student_id


class TestRosterPagination:
    def test_a_page_carries_its_slice_and_the_filtered_total(self, client: TestClient) -> None:
        for name in ("Ada", "Bea", "Cy"):
            _enrol(client, name)

        first = client.get("/api/students", params={"page": 1, "page_size": 2}).json()
        assert [row["display_name"] for row in first["students"]] == ["Ada", "Bea"]
        assert (first["total"], first["page"], first["page_size"]) == (3, 1, 2)

        second = client.get("/api/students", params={"page": 2, "page_size": 2}).json()
        assert [row["display_name"] for row in second["students"]] == ["Cy"]
        assert second["total"] == 3

    def test_search_matches_name_or_email(self, client: TestClient) -> None:
        _enrol(client, "Ada")
        _enrol(client, "Grace")

        hit = client.get("/api/students", params={"search": "grac"}).json()
        assert [row["display_name"] for row in hit["students"]] == ["Grace"]
        assert hit["total"] == 1

    def test_rows_carry_attempt_aggregates(self, client: TestClient, session: Session) -> None:
        set_id = _bank(session)
        _answer_one(client, set_id, "Ada")

        row = client.get("/api/students").json()["students"][0]
        assert row["answered_count"] == 1
        assert row["average_score"] == 100.0
        assert row["score_series"] == [100.0]
        assert row["last_activity_at"] is not None

    def test_the_answered_filter_selects_by_count(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        _answer_one(client, set_id, "Answered")
        _enrol(client, "Untouched")

        unanswered = client.get("/api/students", params={"answered": "0"}).json()
        assert [row["display_name"] for row in unanswered["students"]] == ["Untouched"]

    def test_class_summary_aggregates_every_learner(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        student_id = _answer_one(client, set_id, "Ada")

        summary = client.get("/api/students/class-summary").json()
        assert summary["student_count"] == 1
        assert summary["measured_students"] == 1
        assert summary["average_score"] == 100.0
        assert len(summary["scored_attempts"]) == 1
        assert summary["scored_attempts"][0]["student_id"] == student_id
        assert summary["weakness_cells"], "a scored answer records subtopic weakness"
        assert summary["weakness_cells"][0]["affected"][0]["name"] == "Ada"

    def test_class_summary_scopes_to_the_requested_taxonomy(
        self, client: TestClient, session: Session
    ) -> None:
        set_a = _bank(session)
        set_b = _bank(session)
        version_a = QuestionSetRepository(session).get(set_a).curriculum_version_id
        version_b = QuestionSetRepository(session).get(set_b).curriculum_version_id

        student_a = _answer_one(client, set_a, "Ada")
        _answer_one(client, set_b, "Bea")

        scoped = client.get(
            "/api/students/class-summary", params={"curriculum_version_id": version_a}
        ).json()
        assert [attempt["student_id"] for attempt in scoped["scored_attempts"]] == [student_a]
        assert len(scoped["weakness_cells"]) == 1
        assert [row["name"] for row in scoped["weakness_cells"][0]["affected"]] == ["Ada"]

        unscoped = client.get("/api/students/class-summary").json()
        assert len(unscoped["scored_attempts"]) == 2
        assert len(unscoped["weakness_cells"]) == 2

        other = client.get(
            "/api/students/class-summary", params={"curriculum_version_id": version_b}
        ).json()
        assert [row["name"] for row in other["weakness_cells"][0]["affected"]] == ["Bea"]


class TestStudentResume:
    """A returning browser is recognised by its token, not by re-typing a name."""

    def test_a_stored_token_resumes_into_the_open_session(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        student_id, token = _enrol_with_token(client)
        run_id = _start(client, student_id, set_id)

        response = client.post(
            "/api/students/resume", json={"resume_token": token, "set_version_id": set_id}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["student"]["id"] == student_id
        assert body["active_session"]["id"] == run_id

    def test_a_returning_learner_with_no_open_run_still_resolves(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        student_id, token = _enrol_with_token(client)

        body = client.post(
            "/api/students/resume", json={"resume_token": token, "set_version_id": set_id}
        ).json()
        assert body["student"]["id"] == student_id
        assert body["student"]["resume_token"] == token
        assert body["active_session"] is None

    def test_an_open_run_on_another_set_is_still_surfaced(
        self, client: TestClient, session: Session
    ) -> None:
        """One session at a time: a learner cannot be sent past their open run by
        arriving on a different classroom link."""
        set_a = _bank(session)
        set_b = QuestionSetRepository(session).create(
            label="Week 2", question_ids=[], curriculum_version_id=None
        )
        session.commit()
        student_id, token = _enrol_with_token(client)
        run_id = _start(client, student_id, set_a)

        body = client.post(
            "/api/students/resume", json={"resume_token": token, "set_version_id": set_b.id}
        ).json()
        assert body["student"]["id"] == student_id
        assert body["active_session"]["id"] == run_id
        assert body["active_session"]["set_version_id"] == set_a

    def test_an_ended_session_is_not_offered(self, client: TestClient, session: Session) -> None:
        set_id = _bank(session)
        student_id, token = _enrol_with_token(client)
        run_id = _start(client, student_id, set_id)
        assert client.post(f"/api/training-sessions/{run_id}/end").status_code == 200

        body = client.post(
            "/api/students/resume", json={"resume_token": token, "set_version_id": set_id}
        ).json()
        assert body["active_session"] is None

    def test_an_unknown_token_is_not_found(self, client: TestClient, session: Session) -> None:
        set_id = _bank(session)
        response = client.post(
            "/api/students/resume",
            json={"resume_token": "not-a-real-token", "set_version_id": set_id},
        )
        assert response.status_code == 404


class TestOneActiveSessionGuard:
    """A learner runs exactly one unfinished session, so two attempt streams
    cannot both fold scores into the same per-student BKT state (ADR-041)."""

    def test_a_second_session_is_refused_while_one_is_open(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        student_id = _enrol(client)
        first = _start(client, student_id, set_id)

        response = client.post(
            "/api/training-sessions", json={"student_id": student_id, "set_version_id": set_id}
        )
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert error["code"] == "active_session_exists"
        assert str(first) in error["detail"]

    def test_the_refusal_holds_across_a_different_set(
        self, client: TestClient, session: Session
    ) -> None:
        set_a = _bank(session)
        set_b = QuestionSetRepository(session).create(
            label="Week 2", question_ids=[], curriculum_version_id=None
        )
        session.commit()
        student_id = _enrol(client)
        _start(client, student_id, set_a)

        response = client.post(
            "/api/training-sessions", json={"student_id": student_id, "set_version_id": set_b.id}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "active_session_exists"

    def test_a_new_session_is_allowed_once_the_first_ends(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        student_id = _enrol(client)
        first = _start(client, student_id, set_id)
        assert client.post(f"/api/training-sessions/{first}/end").status_code == 200

        second = _start(client, student_id, set_id)
        assert second != first

    def test_two_learners_each_get_their_own_session(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session)
        ada = _start(client, _enrol(client, "Ada"), set_id)
        grace = _start(client, _enrol(client, "Grace"), set_id)
        assert ada != grace


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

    def test_parsons_publishes_display_indent_but_not_the_solution_order(
        self, client: TestClient, session: Session
    ) -> None:
        set_id = _bank(session, question_type=QuestionType.PARSONS)
        run_id = _start(client, _enrol(client), set_id)

        body = client.get(f"/api/training-sessions/{run_id}/next").json()
        assert body["question_type"] == "parsons"
        assert sorted(body["blocks"], key=lambda block: block["id"]) == [
            {"id": "body", "text": "print(value)", "indent": 1},
            {"id": "head", "text": "for value in items:", "indent": 0},
        ]
        assert "correct_order" not in body
