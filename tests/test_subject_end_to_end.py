"""Phase 2, S5: a Physics course and a Python course, end to end, over the HTTP API.

Each course is created, given a book and a taxonomy, generates one question per chosen type
with a fake LLM, has them approved, freezes them behind its classroom link, and serves them to an
enrolled student who answers each one right and wrong. The only fake is the model: generation,
validation (including ``gradable``), the judges, the review, the frozen set, adaptive serving,
grading and the mastery update are the real code behind the real endpoints.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import book_documents as docs
import pytest
from book_uploads import upload_book
from fastapi.testclient import TestClient
from llm_fakes import MetricJudgeClient
from pydantic import BaseModel

from app.generation.principles import COMMON_SYSTEM
from app.generation.schemas import CodingDraft, MultipleChoiceDraft, shuffle_options
from app.question_types.equation_response import EquationResponseDraft
from app.question_types.numeric_response import NumericResponseDraft
from app.web.routes.api.students import STUDENT_HEADER


def _mcq_answers(draft: MultipleChoiceDraft) -> tuple[str, str]:
    """The (right, wrong) option index the student submits, after the generator's shuffle."""
    right = shuffle_options(draft).correct_option_index
    return str(right), str((right + 1) % len(draft.options))


PHYSICS_TAXONOMY = {
    "schema_version": "1",
    "label": "Mechanics",
    "topics": [{"name": "Kinematics", "subtopics": [{"name": "Free fall"}, {"name": "Energy"}]}],
}
PYTHON_TAXONOMY = {
    "schema_version": "1",
    "label": "Intro Python",
    "topics": [{"name": "Basics", "subtopics": [{"name": "Values"}, {"name": "Variables"}]}],
}


class SwitchableRecorder(MetricJudgeClient):
    """One fake for generation and judging whose draft the test swaps per request.

    Records the system prompt of every call, so the test can tell the generator's prompt from
    the judges' panel.
    """

    def __init__(self) -> None:
        super().__init__()
        self.judge_systems: list[str] = []

    def use(self, draft: BaseModel) -> None:
        self.draft = draft
        self.topic_id = draft.topic_id  # type: ignore[attr-defined]
        self.subtopic_ids = list(draft.subtopic_ids)  # type: ignore[attr-defined]

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        if self.draft is None or not isinstance(self.draft, response_model):
            self.judge_systems.append(system)
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kwargs
        )


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> SwitchableRecorder:
    """Every model call the API makes -- generator and judges -- goes to one recording fake."""
    fake = SwitchableRecorder()
    monkeypatch.setattr("app.generation.base.get_structured_client", lambda *a, **k: fake)
    monkeypatch.setattr("app.evaluation.service.get_structured_client", lambda *a, **k: fake)
    return fake


# --------------------------------------------------------------------------- helpers


def _in(course_id: int) -> dict[str, str]:
    return {"X-Course-Id": str(course_id)}


def _physics_book() -> dict[str, Any]:
    book = copy.deepcopy(docs.think_python())
    book["title"] = "University Physics"
    book["author"] = "A. Physicist"
    book["source_filename"] = "physics.pdf"
    texts = [
        ("Free fall", "Near Earth's surface a dropped body accelerates downward at g."),
        ("Velocity", "Velocity is the rate of change of position with time."),
        ("Kinetic energy", "A moving body of mass m and speed v carries kinetic energy."),
        ("Potential energy", "Lifting a mass m through height h stores energy m g h."),
    ]
    sections = [s for chapter in book["chapters"] for s in chapter["sections"]]
    for section, (title, text) in zip(sections, texts, strict=True):
        section["title"], section["text"] = title, text
    return book


def _course(client: TestClient, name: str, subject: str, types: list[str]) -> int:
    response = client.post(
        "/api/courses", json={"name": name, "subject": subject, "question_types": types}
    )
    assert response.status_code == 201, response.text
    assert response.json()["question_types"] == types
    return response.json()["id"]


def _material(
    client: TestClient, course_id: int, book: dict[str, Any], taxonomy: dict[str, Any]
) -> tuple[int, int, int, list[int]]:
    """Import the book and the taxonomy into the course: (version, section, topic, subtopics)."""
    uploaded = upload_book(
        client,
        headers=_in(course_id),
        files={"file": ("book.json", docs.to_bytes(book), "application/json")},
    )
    sections = client.get(f"/api/books/{uploaded['id']}/sections", headers=_in(course_id))
    assert sections.status_code == 200, sections.text

    imported = client.post(
        "/api/curriculum/versions",
        headers=_in(course_id),
        files={"file": ("taxonomy.json", json.dumps(taxonomy).encode(), "application/json")},
    )
    assert imported.status_code == 201, imported.text
    approved = client.get("/api/curriculum/approved", headers=_in(course_id))
    assert approved.status_code == 200, approved.text
    version = approved.json()
    assert version["version"]["id"] == imported.json()["version"]["id"]
    topic = version["topics"][0]
    return (
        version["version"]["id"],
        sections.json()["sections"][0]["id"],
        topic["id"],
        [subtopic["id"] for subtopic in topic["subtopics"]],
    )


def _generate(
    client: TestClient,
    fake: SwitchableRecorder,
    course_id: int,
    section_id: int,
    question_type: str,
    draft: BaseModel,
) -> dict[str, Any]:
    """Generate one question through the API and return its detail."""
    fake.use(draft)
    generated = client.post(
        "/api/questions/generate",
        headers=_in(course_id),
        json={"question_type": question_type, "difficulty": "easy", "section_ids": [section_id]},
    )
    assert generated.status_code == 201, generated.text
    (question_id,) = generated.json()["question_ids"]
    detail = client.get(f"/api/questions/{question_id}", headers=_in(course_id))
    assert detail.status_code == 200, detail.text
    return detail.json()


def _assert_valid_and_judged(detail: dict[str, Any]) -> None:
    checks = {check["name"]: check["passed"] for check in detail["validation_checks"]}
    failed = [name for name, passed in checks.items() if not passed]
    assert failed == [], detail["validation_checks"]
    assert checks.get("gradable") is True, sorted(checks)
    assert detail["validation_passed"] is True
    assert detail["question"]["status"] == "validation_passed"
    evaluation = detail["pedagogical_eval"]
    assert evaluation is not None, detail
    assert (evaluation["status"], evaluation["gate"]) == ("completed", "approved"), evaluation


def _approve_and_publish(
    client: TestClient, course_id: int, version_id: int, question_ids: list[int]
) -> int:
    """Approve every question, sync the taxonomy's classroom link, return the set students join."""
    for question_id in question_ids:
        review = client.post(f"/api/questions/{question_id}/review", json={"decision": "approve"})
        assert review.status_code == 201, review.text
    synced = client.post(f"/api/question-sets/taxonomy/{version_id}/sync", headers=_in(course_id))
    assert synced.status_code == 201, synced.text
    assert synced.json()["question_count"] == len(question_ids)
    # What the student's join page reads (public, no course header).
    link = client.get(f"/api/question-sets/taxonomy/{version_id}")
    assert link.status_code == 200, link.text
    assert link.json()["id"] == synced.json()["id"]
    return link.json()["id"]


def _enrol(client: TestClient, name: str) -> int:
    slug = name.lower().replace(" ", ".")
    response = client.post(
        "/api/students", json={"display_name": name, "email": f"{slug}@example.edu"}
    )
    assert response.status_code == 201, response.text
    # The student page sends the learner's token on every run call (ADR-060).
    client.headers[STUDENT_HEADER] = response.json()["resume_token"]
    return response.json()["id"]


def _run(
    client: TestClient,
    student_id: int,
    set_id: int,
    answers: dict[int, list[tuple[str, float]]],
    secrets: dict[int, list[str]],
) -> list[dict[str, Any]]:
    """Serve questions until every planned answer has been given; returns every answer given.

    ``answers`` maps a question id to the (answer, expected score) pairs still to submit, in
    order. Each served question gets its next pending answer; a question with none left is
    answered with its first answer again (and the score is not checked). ``secrets`` are strings
    the served payload must never contain.
    """
    started = client.post(
        "/api/training-sessions", json={"student_id": student_id, "set_version_id": set_id}
    )
    assert started.status_code == 201, started.text
    session_id = started.json()["id"]
    pending = {question_id: list(plan) for question_id, plan in answers.items()}
    first = {question_id: plan[0][0] for question_id, plan in answers.items()}
    scored: list[dict[str, Any]] = []
    for _ in range(60):
        if not any(pending.values()):
            break
        served = client.get(f"/api/training-sessions/{session_id}/next")
        assert served.status_code == 200, served.text
        body = served.json()
        question_id = body["question_id"]
        assert question_id in answers, body
        published = json.dumps(body)
        for secret in secrets.get(question_id, []):
            assert secret not in published, (secret, body)
        if pending[question_id]:
            answer, expected = pending[question_id].pop(0)
        else:
            answer, expected = first[question_id], None
        result = client.post(f"/api/attempts/{body['attempt_id']}/answer", json={"answer": answer})
        assert result.status_code == 200, result.text
        out = result.json() | {"served": body, "answer": answer, "checked": expected is not None}
        if expected is not None:
            assert out["score"] == expected, (question_id, answer, out)
        scored.append(out)
    else:
        raise AssertionError(f"Some planned answers were never served: {pending}")
    ended = client.post(f"/api/training-sessions/{session_id}/end")
    assert ended.status_code == 200, ended.text
    return scored


def _progress(client: TestClient, student_id: int) -> dict[str, Any]:
    response = client.get(f"/api/students/{student_id}/progress")
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- physics


def test_a_physics_course_runs_end_to_end(client: TestClient, fake_llm: SwitchableRecorder) -> None:
    course_id = _course(
        client,
        "Physics 101",
        "physics",
        ["multiple_choice", "numeric_response", "equation_response"],
    )
    version_id, section_id, topic_id, (free_fall, energy) = _material(
        client, course_id, _physics_book(), PHYSICS_TAXONOMY
    )

    drafts = {
        "multiple_choice": MultipleChoiceDraft(
            topic_id=topic_id,
            subtopic_ids=[free_fall],
            prompt="A ball is dropped from rest. Which way does it accelerate?",
            options=["Downwards", "Upwards", "It does not accelerate"],
            correct_option_index=0,
            explanation="Gravity pulls it towards the ground.",
        ),
        "numeric_response": NumericResponseDraft(
            topic_id=topic_id,
            subtopic_ids=[free_fall],
            prompt="A ball is dropped from rest on Earth. What is its acceleration while it falls?",
            value=9.81,
            unit="m/s^2",
            relative_tolerance=0.01,
            calculation="9.81",
            explanation="Near Earth's surface every falling body accelerates at g.",
        ),
        "equation_response": EquationResponseDraft(
            topic_id=topic_id,
            subtopic_ids=[energy],
            prompt="Write the gravitational potential energy of a mass m lifted a height h.",
            expected="m*g*h",
            variables=["m", "g", "h"],
            explanation="The work done lifting the mass is its weight times the height.",
        ),
    }
    details = {
        question_type: _generate(client, fake_llm, course_id, section_id, question_type, draft)
        for question_type, draft in drafts.items()
    }

    # Generation: the Physics system prompt, never the Python one, for all three types.
    systems = [call["system"] for call in fake_llm.generation_calls]
    assert len(systems) == 3
    assert all(system == systems[0] for system in systems)
    assert systems[0] != COMMON_SYSTEM
    assert "python" not in systems[0].lower()

    # Validation, gradable included, and the Physics judge panel.
    for detail in details.values():
        _assert_valid_and_judged(detail)
    python_rubric = _python_rubric_version()
    rubrics = {detail["pedagogical_eval"]["rubric_version"] for detail in details.values()}
    assert len(rubrics) == 1 and python_rubric not in rubrics
    assert fake_llm.judge_systems
    assert not any("python" in system.lower() for system in fake_llm.judge_systems)

    ids = {question_type: detail["question"]["id"] for question_type, detail in details.items()}
    set_id = _approve_and_publish(client, course_id, version_id, list(ids.values()))
    student_id = _enrol(client, "Ada Physics")

    mcq, numeric, equation = (
        ids["multiple_choice"],
        ids["numeric_response"],
        ids["equation_response"],
    )
    right_wrong = _mcq_answers(drafts["multiple_choice"])
    secrets = {
        numeric: ["9.81", "relative_tolerance", "explanation"],
        equation: ["m*g*h", "expected", "explanation"],
        mcq: ["correct_option_index", "explanation"],
    }
    first = _run(
        client,
        student_id,
        set_id,
        {
            mcq: [(right_wrong[1], 0), (right_wrong[0], 100)],
            numeric: [("9.81 kg", 0), ("9.81 m/s^2", 100)],
            equation: [("m*g", 0), ("g*h*m", 100)],
        },
        secrets,
    )
    # A second learner: the first has mastered the only topic, so a new run of theirs would
    # (rightly) report the curriculum as complete.
    second_student = _enrol(client, "Bea Physics")
    second = _run(
        client,
        second_student,
        set_id,
        {
            mcq: [(right_wrong[1], 0)],
            numeric: [("12 m/s^2", 0), ("981 cm/s^2", 100)],
            equation: [("m*g", 0), ("h m g", 100)],
        },
        secrets,
    )
    scored = first + second

    # The served question shows each type's answer hint and no answer key.
    served = {out["question_id"]: out["served"] for out in scored}
    assert served[mcq]["options"] == shuffle_options(drafts["multiple_choice"]).options
    assert served[mcq]["answer_hint"] is None
    assert served[numeric]["answer_hint"] == "Give a number with its unit, e.g. in m/s^2."
    assert served[equation]["answer_hint"].startswith("Write an expression using m, g")
    assert all(served[q]["options"] is None for q in (numeric, equation))

    # A wrong dimension says why (the grader's format message), ahead of the explanation;
    # a wrong number in the right unit just gets the explanation.
    wrong_unit = next(o for o in scored if o["answer"] == "9.81 kg")
    assert "doesn't match" in wrong_unit["detail"]
    assert wrong_unit["detail"].endswith(drafts["numeric_response"].explanation)
    wrong_value = next(o for o in scored if o["answer"] == "12 m/s^2")
    assert wrong_value["detail"] == drafts["numeric_response"].explanation

    # Each student's progress reflects exactly their own answers.
    progress = _progress(client, student_id)
    assert progress["answered"] == len(first)
    by_question: dict[int, list[float]] = {}
    for attempt in progress["recent_attempts"]:
        by_question.setdefault(attempt["question_id"], []).append(attempt["score"])
    for question_id in ids.values():
        assert 100 in by_question[question_id] and 0 in by_question[question_id], by_question
    assert [topic["topic_id"] for topic in progress["topics"]] == [topic_id]
    assert progress["topics"][0]["observations"] == progress["answered"]
    assert {row["subtopic_id"] for row in progress["subtopics"]} == {free_fall, energy}
    assert len(progress["sessions"]) == 1
    assert progress["average_score"] == sum(o["score"] for o in first) / len(first)
    # Every right answer raised the topic's mastery and every wrong one lowered it.
    for out in first:
        moved = out["mastery_after"] - out["mastery_before"]
        assert moved > 0 if out["score"] == 100 else moved < 0, out

    other = _progress(client, second_student)
    assert other["answered"] == len(second)
    assert sorted(a["score"] for a in other["recent_attempts"]) == sorted(
        o["score"] for o in second
    )


def _python_rubric_version() -> str:
    from app.evaluation.prompts import rubric_version_for
    from app.subjects import PYTHON_PROFILE

    return rubric_version_for(PYTHON_PROFILE)


# --------------------------------------------------------------------------- python


def test_a_python_course_runs_the_same_way(
    client: TestClient, fake_llm: SwitchableRecorder
) -> None:
    course_id = _course(client, "CS 1", "intro_python", ["multiple_choice", "coding"])
    version_id, section_id, topic_id, (values, variables) = _material(
        client, course_id, docs.think_python(), PYTHON_TAXONOMY
    )
    drafts = {
        "multiple_choice": MultipleChoiceDraft(
            topic_id=topic_id,
            subtopic_ids=[values],
            prompt="Which of these values is a string?",
            options=["42", "'42'", "4.2"],
            correct_option_index=1,
            explanation="Quotes make a string.",
        ),
        "coding": CodingDraft(
            topic_id=topic_id,
            subtopic_ids=[variables],
            prompt="Read a whole number from input, store it in a variable and print it doubled.",
            reference_solution="n = int(input())\nprint(n * 2)\n",
            tests=[{"stdin": "3\n", "stdout": "6"}, {"stdin": "21\n", "stdout": "42"}],
            explanation="int() turns the text into a number; the variable holds it.",
        ),
    }
    details = {
        question_type: _generate(client, fake_llm, course_id, section_id, question_type, draft)
        for question_type, draft in drafts.items()
    }

    assert [call["system"] for call in fake_llm.generation_calls] == [COMMON_SYSTEM] * 2
    for detail in details.values():
        _assert_valid_and_judged(detail)
    assert {d["pedagogical_eval"]["rubric_version"] for d in details.values()} == {
        _python_rubric_version()
    }

    ids = {question_type: detail["question"]["id"] for question_type, detail in details.items()}
    set_id = _approve_and_publish(client, course_id, version_id, list(ids.values()))
    student_id = _enrol(client, "Ada Python")
    mcq, coding = ids["multiple_choice"], ids["coding"]
    right, wrong = _mcq_answers(drafts["multiple_choice"])
    scored = _run(
        client,
        student_id,
        set_id,
        {
            mcq: [(wrong, 0), (right, 100)],
            coding: [("print(int(input()) + 2)", 0), ("print(int(input()) * 2)", 100)],
        },
        {coding: ["n * 2", "reference_solution", "stdout"], mcq: ["correct_option_index"]},
    )

    coded = [o for o in scored if o["question_id"] == coding and o["checked"]]
    assert [(o["passed_tests"], o["total_tests"]) for o in coded] == [(0, 2), (2, 2)]
    progress = _progress(client, student_id)
    assert progress["answered"] == len(scored)
    assert [topic["topic_id"] for topic in progress["topics"]] == [topic_id]
