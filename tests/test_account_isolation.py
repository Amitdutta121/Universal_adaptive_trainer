"""An account is the isolation boundary (ADR-060): a new signup sees and touches only its own data.

Everything here runs the real app: real cookie login, the real ``X-Course-Id`` check and
the real student-token check, with no ``conftest`` override. Professor A has a course full of
data; accounts are made by ``python -m app.auth.create_user`` (the path public signup will
take in M3). The intruder -- a plain professor, and a superuser, which grants nothing extra --
must get empty lists everywhere and a 404 for every one of A's ids, wherever it is put.

The route sweep enumerates ``app.routes``, so a new route fails
:func:`test_every_route_is_classified` until it is given a probe or a reasoned place in
:data:`ALLOWLIST`.
"""

from __future__ import annotations

import io
import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.create_user import main as create_user_cli
from app.config import Settings
from app.domain.enums import (
    CurriculumStatus,
    Difficulty,
    QuestionStatus,
    QuestionType,
    ReviewDecision,
)
from app.persistence.models import (
    BookRow,
    BookSectionRow,
    CourseRow,
    CurriculumVersionRow,
    CustomJudgeRow,
    GenerationRoundRow,
    JudgeBatchRunRow,
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    QuestionSetAliasRow,
    QuestionSetupRow,
    QuestionSubtopicRow,
    StudentAttemptRow,
    StudentRow,
    StudentSubtopicWeaknessRow,
    StudentTopicMasteryRow,
    SubtopicRow,
    TopicRow,
    TrainingSessionRow,
    TypeInstructionRow,
    UserRow,
)
from app.persistence.repositories import QuestionSetRepository
from app.subjects import profile_for_course_id
from app.web.routes.api.coverage import get_generation_client
from app.web.routes.api.curriculum import get_draft_client
from app.web.routes.api.deps import COURSE_HEADER
from app.web.routes.api.retrieval import get_query_embedder
from app.web.routes.api.setup import get_setup_client
from app.web.routes.api.students import STUDENT_HEADER

#: Written into every text field of A's rows; no response the intruder gets may contain it.
SECRET = "ALICE-PRIVATE"
PASSWORD = "a-long-enough-passphrase"
ALICE_EMAIL = "alice@example.edu"

#: Routes the sweep leaves out on purpose, each with the reason.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("GET", "/api/health"): "public liveness probe; reads no account data",
    ("GET", "/api/config"): "public enum vocabularies and limits; reads no account data",
    ("POST", "/api/auth/login"): "public; checked by test_create_user.py and the first-login test",
    ("POST", "/api/auth/logout"): "ends the caller's own session only",
    ("GET", "/api/auth/me"): "returns the caller only; checked by the first-login test",
    ("GET", "/api/courses/catalog"): "the shipped subject/question-type catalogue, same for all",
    ("GET", "/api/books/document-guide"): "static description of the book document format",
    ("GET", "/api/curriculum/document-guide"): "static description of the taxonomy format",
    ("POST", "/api/questions/batch-plan"): "pure compile of the posted spec; touches no row",
    ("POST", "/api/curriculum/drafts"): "LLM draft from the posted brief; nothing is read or saved",
    ("POST", "/api/courses"): "creates the caller's own course; owner stamping tested below",
    ("POST", "/api/students"): "public student enrolment; creates a new learner, reads nothing",
    ("POST", "/api/students/resume"): "public, but keyed by a 256-bit resume token, not an id",
    ("GET", "/api/question-sets/prod"): (
        "public join lobby for the installation-wide prod link (ADR-041); repointing it is "
        "guarded, see test_the_prod_link_cannot_be_taken_over"
    ),
    ("GET", "/api/question-sets/taxonomy/{curriculum_version_id}"): (
        "public join lobby: a classroom link is a public capability (ADR-041). Known gap: "
        "the id is sequential, so a guessed link joins that class (needs an unguessable join "
        "code; not part of M2)"
    ),
    ("GET", "/api/question-sets/{set_version_id}"): "public join lobby; same known gap as above",
}

#: Path parameters that are not row ids: any value works, and the course header decides.
NON_ID_PARAMS = {"metric": "issues", "question_type": "true_false", "rule_index": "0"}

#: Bodies that pass validation, so a request reaches the handler's own ownership check.
#: ``"{name}"`` is replaced by A's id of that name.
BODIES: dict[tuple[str, str], Any] = {
    ("PATCH", "/api/courses/{course_id}"): {"name": "Taken"},
    ("PATCH", "/api/books/{book_id}"): {"title": "Taken"},
    ("PATCH", "/api/curriculum/versions/{version_id}"): {"label": "Taken"},
    ("PUT", "/api/curriculum/versions/{version_id}/tree"): {"label": "Taken", "topics": []},
    ("PATCH", "/api/curriculum/topics/{topic_id}"): {"name": "Taken"},
    ("PATCH", "/api/curriculum/subtopics/{subtopic_id}"): {"name": "Taken"},
    ("POST", "/api/questions/{question_id}/regenerate"): {"feedback": "Make it harder."},
    ("POST", "/api/questions/{question_id}/review"): {"decision": "approve"},
    ("PATCH", "/api/custom-judges/{judge_id}"): {"enabled": False},
    ("POST", "/api/attempts/{attempt_id}/answer"): {"answer": "true"},
    ("PUT", "/api/judge-prompts/{metric}"): {"system_prompt": "Taken"},
    ("POST", "/api/questions/generate"): {
        "curriculum_version_id": "{version}",
        "question_type": "true_false",
        "difficulty": "easy",
        "section_ids": ["{section}"],
    },
    ("POST", "/api/questions/generate-batch"): {"chunks": [{"section_id": "{section}", "easy": 1}]},
    ("POST", "/api/coverage/generation-runs"): {
        "targets": [{"subtopic_id": "{subtopic}", "difficulty": "easy"}]
    },
    ("POST", "/api/setup/suggest"): {"curriculum_version_id": "{version}"},
    ("POST", "/api/setup"): {
        "curriculum_version_id": "{version}",
        "approved_styles": [],
        "cell_targets": [],
    },
    ("POST", "/api/rounds"): {"setup_id": "{setup}"},
    ("POST", "/api/custom-judges"): {"curriculum_version_id": "{version}", "rule_text": "Taken"},
    ("POST", "/api/training-sessions"): {"student_id": "{student}", "set_version_id": "{qset}"},
    ("POST", "/api/evaluation/batch-runs"): {"question_ids": ["{question}"]},
    ("POST", "/api/question-sets"): {"label": "Taken"},
}

#: Ids of A's rows that a query string may carry, by parameter name.
QUERY_IDS = {
    "book_id": "book",
    "curriculum_version_id": "version",
    "set_version_id": "qset",
    "subtopic_id": "subtopic",
    "student_id": "student",
    "section_ids": "section",
    "section_id": "section",
}

#: Path parameter -> which of A's ids goes in it.
PATH_IDS = {
    "course_id": "course",
    "book_id": "book",
    "section_id": "section",
    "version_id": "version",
    "curriculum_version_id": "version",
    "topic_id": "topic",
    "subtopic_id": "subtopic",
    "question_id": "question",
    "student_id": "student",
    "training_session_id": "run",
    "attempt_id": "attempt",
    "run_id": "batch_run",
    "round_id": "round",
    "judge_id": "custom_judge",
    "set_version_id": "qset",
}

#: Lists a brand-new account legitimately sees filled: shipped content, not anyone's data.
SHIPPED_LISTS = {
    ("GET", "/api/judge-prompts"): {"prompts"},
    ("GET", "/api/judge-prompts/stats"): {"judges"},  # one zeroed row per shipped judge
    ("GET", "/api/instructions"): {"instructions"},
    ("GET", "/api/styles"): {"styles"},
    # One zeroed row per shipped judge metric.
    ("GET", "/api/calibration/results"): {"metrics"},
    ("GET", "/api/calibration/quadrant"): {"metrics", "unattributable_metrics"},
}


#: Single-resource reads that are a 404 until the new account makes the thing.
NOTHING_YET = {"/api/curriculum/approved": "the course's approved taxonomy; none yet"}
#: GETs without required parameters that are still not lists.
NOT_LISTS = {
    "/api/retrieval/sections": (
        "a search: needs query or subtopic_id; subtopic_id is probed by the 404 sweep"
    ),
}


@dataclass
class Seed:
    course: int
    book: int
    section: int
    version: int
    topic: int
    subtopic: int
    question: int
    qset: int
    student: int
    run: int
    attempt: int
    batch_run: str
    setup: int
    round: int
    custom_judge: int


# ---------------------------------------------------------------- accounts and seed


def _create_account(monkeypatch: pytest.MonkeyPatch, email: str, *extra: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert create_user_cli(["--email", email, "--password-stdin", *extra]) == 0


def _login(app: FastAPI, email: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/auth/login", data={"username": email, "password": PASSWORD})
    assert response.status_code == 204, response.text
    return client


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    from app.main import create_app

    application = create_app(settings)
    # Never reached -- every probe is refused first -- but building the real ones needs an
    # LLM provider, which the suite never has.
    application.dependency_overrides[get_generation_client] = lambda: None
    application.dependency_overrides[get_draft_client] = lambda: None
    application.dependency_overrides[get_setup_client] = lambda: None
    application.dependency_overrides[get_query_embedder] = object
    with TestClient(application):  # runs the lifespan: migrations, schema check
        yield application


@pytest.fixture
def alice(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _create_account(monkeypatch, ALICE_EMAIL)
    with _login(app, ALICE_EMAIL) as client:
        yield client


@pytest.fixture
def seed(alice: TestClient, session: Session) -> Seed:
    """A's course with a row in every table a professor route reads, plus ownerless rows."""
    created = alice.post("/api/courses", json={"name": f"{SECRET} course"})
    assert created.status_code == 201, created.text
    course_id = created.json()["id"]
    owner = session.scalars(select(UserRow).where(UserRow.email == ALICE_EMAIL)).one()

    rows = _content(session, course_id, label=SECRET)
    # Ownerless data a fresh account must never see either (ADR-060): a course with no owner,
    # and a book and taxonomy that belong to no course.
    orphan_course = CourseRow(name=f"{SECRET} orphan course", owner_id=None)
    session.add(orphan_course)
    session.flush()
    _content(session, orphan_course.id, label=f"{SECRET} orphan")
    _content(session, None, label=f"{SECRET} courseless")
    session.add(
        TypeInstructionRow(
            subject=profile_for_course_id(session, course_id).personal_key,
            question_type=QuestionType.TRUE_FALSE,
            instruction=f"{SECRET} learned instruction",
        )
    )
    session.add(QuestionSetAliasRow(alias=f"taxonomy-{rows.version}", set_version_id=rows.qset))
    session.add(QuestionSetAliasRow(alias="prod", set_version_id=rows.qset))
    session.commit()
    assert owner.id is not None

    edited = alice.put(
        "/api/judge-prompts/issues",
        headers={COURSE_HEADER: str(course_id)},
        json={"system_prompt": f"{SECRET} judge prompt"},
    )
    assert edited.status_code == 200, edited.text
    return rows


def _content(session: Session, course_id: int | None, *, label: str) -> Seed:
    book = BookRow(course_id=course_id, title=f"{label} book", original_filename="a.json")
    subtopic = SubtopicRow(name=f"{label} subtopic", position=0)
    topic = TopicRow(name=f"{label} topic", position=0, subtopics=[subtopic])
    version = CurriculumVersionRow(
        label=f"{label} taxonomy",
        course_id=course_id,
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
        topics=[topic],
    )
    session.add_all([book, version])
    session.flush()
    from app.domain.enums import StructureConfidence, StructureSource

    section = BookSectionRow(
        book_id=book.id,
        title=f"{label} section",
        text=f"{label} section text",
        structure_source=next(iter(StructureSource)),
        structure_confidence=next(iter(StructureConfidence)),
    )
    question = QuestionRow(
        prompt=f"{label} question",
        original_prompt=f"{label} question",
        curriculum_version_id=version.id,
        topic_id=topic.id,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=Difficulty.EASY,
        status=QuestionStatus.APPROVED,
        content={"prompt": f"{label} question", "correct_answer": True},
        generator_name="base",
        generator_version="1",
    )
    session.add_all([section, question])
    session.flush()
    session.add(QuestionSubtopicRow(question_id=question.id, subtopic_id=subtopic.id))
    session.add(
        QuestionEvaluationRow(question_id=question.id, run_id=f"{label}-eval", evaluation={})
    )
    session.add(
        ProfessorReviewRow(
            question_id=question.id, decision=ReviewDecision.APPROVE, comment=f"{label} review"
        )
    )
    qset = QuestionSetRepository(session).create(
        label=f"{label} set", question_ids=[question.id], curriculum_version_id=version.id
    )
    student = StudentRow(display_name=f"{label} student", email="ada@example.edu")
    session.add(student)
    session.flush()
    run = TrainingSessionRow(student_id=student.id, set_version_id=qset.id)
    session.add(run)
    session.flush()
    attempt = StudentAttemptRow(
        session_id=run.id,
        student_id=student.id,
        question_id=question.id,
        subtopic_id=subtopic.id,
        requested_difficulty=Difficulty.EASY,
        served_difficulty=Difficulty.EASY,
        answer="true",
        score=1.0,
        answered_at=datetime.now(UTC),
    )
    session.add_all(
        [
            attempt,
            StudentTopicMasteryRow(student_id=student.id, topic_id=topic.id, observations=1),
            StudentSubtopicWeaknessRow(
                student_id=student.id, subtopic_id=subtopic.id, observations=1
            ),
        ]
    )
    batch = JudgeBatchRunRow(run_id=f"run-{uuid.uuid4().hex[:12]}", course_id=course_id)
    setup = QuestionSetupRow(curriculum_version_id=version.id)
    judge = CustomJudgeRow(curriculum_version_id=version.id, rule_text=f"{label} rule")
    session.add_all([batch, setup, judge])
    session.flush()
    generation_round = GenerationRoundRow(setup_id=setup.id, number=1)
    session.add(generation_round)
    session.flush()
    return Seed(
        course=course_id or 0,
        book=book.id,
        section=section.id,
        version=version.id,
        topic=topic.id,
        subtopic=subtopic.id,
        question=question.id,
        qset=qset.id,
        student=student.id,
        run=run.id,
        attempt=attempt.id,
        batch_run=batch.run_id,
        setup=setup.id,
        round=generation_round.id,
        custom_judge=judge.id,
    )


@pytest.fixture(params=["professor", "superuser"])
def intruder(
    request: pytest.FixtureRequest,
    app: FastAPI,
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, int]]:
    """A fresh account (logged in) and the one course it creates for itself."""
    email = f"new-{request.param}@example.edu"
    _create_account(monkeypatch, email, *(["--superuser"] if request.param == "superuser" else []))
    with _login(app, email) as client:
        assert client.get("/api/courses").json()["courses"] == []
        course = client.post("/api/courses", json={"name": "My course"}).json()["id"]
        yield client, course


# ---------------------------------------------------------------- the route sweep


def _routes(app: FastAPI) -> list[tuple[str, str, APIRoute]]:
    out = []
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        if isinstance(route, APIRoute) and context.path.startswith("/api"):
            out.extend((method, context.path, route) for method in sorted(context.methods))
    return out


def _depends_on(route: APIRoute, name: str) -> bool:
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        if getattr(dependency.call, "__name__", "") == name:
            return True
        stack.extend(dependency.dependencies)
    return False


def _router_deps(app: FastAPI, method: str, path: str) -> set[str]:
    """Names of every dependency the mounted route runs, router-level ones included."""
    for context in iter_route_contexts(app.routes):
        if context.path == path and method in context.methods:
            names: set[str] = set()
            stack = list(context.dependant.dependencies)
            while stack:
                dependency = stack.pop()
                names.add(getattr(dependency.call, "__name__", ""))
                stack.extend(dependency.dependencies)
            return names
    raise AssertionError(f"{method} {path} is not mounted")


def _fill(value: Any, ids: dict[str, Any]) -> Any:
    if isinstance(value, str) and re.fullmatch(r"\{\w+\}", value):
        return ids[value.strip("{}")]
    if isinstance(value, dict):
        return {key: _fill(item, ids) for key, item in value.items()}
    if isinstance(value, list):
        return [_fill(item, ids) for item in value]
    return value


def _url(path: str, ids: dict[str, Any]) -> str:
    def one(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in NON_ID_PARAMS:
            return NON_ID_PARAMS[name]
        return str(ids[PATH_IDS[name]])

    return re.sub(r"\{(\w+)\}", one, path)


def _path_ids(path: str) -> list[str]:
    return [name for name in re.findall(r"\{(\w+)\}", path) if name in PATH_IDS]


def _query_ids(route: APIRoute) -> list[str]:
    return [param.alias for param in route.dependant.query_params if param.alias in QUERY_IDS]


def _required_query(route: APIRoute) -> list[str]:
    return [param.alias for param in route.dependant.query_params if param.field_info.is_required()]


def _assert_private(response: Any, what: str) -> None:
    assert SECRET not in response.text, f"{what} leaked A's data: {response.text[:400]}"
    assert ALICE_EMAIL not in response.text, f"{what} leaked A's email"


def _probes(app: FastAPI, seed: Seed, own_course: int):
    """Every (description, method, url, headers, body, expected) the sweep sends."""
    ids = vars(seed)
    for method, path, route in _routes(app):
        if (method, path) in ALLOWLIST:
            continue
        names = _router_deps(app, method, path)
        scoped = "_course_scope" in names
        body = _fill(BODIES.get((method, path)), ids)
        default_query = {
            name: ids[QUERY_IDS[name]] if name in QUERY_IDS else "x"
            for name in _required_query(route)
        }
        own = {COURSE_HEADER: str(own_course)}
        if scoped:
            # A's course named in the header: refused before anything else runs.
            yield (
                f"{method} {path} with A's X-Course-Id",
                method,
                _url(path, ids),
                {COURSE_HEADER: str(seed.course)},
                body,
                default_query,
            )
        if _path_ids(path):
            yield (f"{method} {path} with A's path id", method, _url(path, ids), own, body, {})
        for name in _query_ids(route):
            query = {**default_query, name: ids[QUERY_IDS[name]]}
            yield (f"{method} {path}?{name}= A's id", method, _url(path, ids), own, body, query)
        if re.search(r'"\{\w+\}"', json.dumps(BODIES.get((method, path)))):
            yield (f"{method} {path} with A's ids in the body", method, path, own, body, {})


def test_every_route_is_classified(app: FastAPI) -> None:
    """A new route must be reachable by the sweep or named in the allowlist with a reason."""
    unclassified = []
    for method, path, route in _routes(app):
        if (method, path) in ALLOWLIST:
            continue
        names = _router_deps(app, method, path)
        guarded = "_course_scope" in names or "_learner" in names
        lists = method == "GET" and not _path_ids(path) and not _required_query(route)
        if not (guarded or _path_ids(path) or lists):
            unclassified.append(f"{method} {path}")
        needs_body = method in {"POST", "PUT", "PATCH"} and _path_ids(path) and route.body_field
        if needs_body and (method, path) not in BODIES:
            unclassified.append(f"{method} {path} (needs a body in BODIES)")
    assert unclassified == []


def test_a_new_account_gets_404_for_every_id_of_another_account(
    app: FastAPI, seed: Seed, intruder: tuple[TestClient, int]
) -> None:
    client, own_course = intruder
    failures = []
    for what, method, url, headers, body, query in _probes(app, seed, own_course):
        response = client.request(method, url, headers=headers, json=body, params=query)
        if response.status_code != 404:
            failures.append(f"{what}: {response.status_code} {response.text[:200]}")
        _assert_private(response, what)
    assert failures == [], "\n".join(failures)


def test_a_new_account_sees_only_empty_lists(
    app: FastAPI, seed: Seed, intruder: tuple[TestClient, int]
) -> None:
    client, own_course = intruder
    checked: list[str] = []
    leaks: list[str] = []
    for method, path, route in _routes(app):
        if method != "GET" or _path_ids(path) or _required_query(route):
            continue
        if (method, path) in ALLOWLIST or path in NOT_LISTS:
            continue
        response = client.get(path, headers={COURSE_HEADER: str(own_course)})
        _assert_private(response, path)
        if path in NOTHING_YET:
            assert response.status_code == 404, f"{path}: {response.status_code}"
            continue
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"
        _assert_private(response, path)
        if path in {"/api/courses", "/api/courses/overview"}:
            # The account's one course; the list was empty before it made it (``intruder``).
            courses = response.json()["courses"]
            ids = [entry.get("course", entry)["id"] for entry in courses]
            assert ids == [own_course], f"{path}: {ids}"
            checked.append(path)
            continue
        filled = _filled_lists(response.json(), SHIPPED_LISTS.get((method, path), set()))
        if filled:
            leaks.append(f"{path} lists {sorted(filled)}: {response.text[:300]}")
        checked.append(path)
    assert leaks == [], "\n".join(leaks)
    # Guard against the sweep silently checking nothing.
    assert {"/api/books", "/api/questions", "/api/students", "/api/courses"} <= set(checked)

    counts = client.get("/api/counts", headers={COURSE_HEADER: str(own_course)}).json()
    assert set(counts.values()) == {0}, counts


def _filled_lists(payload: Any, shipped: set[str], key: str = "") -> set[str]:
    """Names of every non-empty list in a JSON payload, skipping ``shipped`` subtrees."""
    found: set[str] = set()
    if isinstance(payload, list):
        if payload:
            found.add(key or "<root>")
        for item in payload:
            found |= _filled_lists(item, shipped, key)
    elif isinstance(payload, dict):
        for name, value in payload.items():
            if name not in shipped:
                found |= _filled_lists(value, shipped, name)
    return found


def test_another_account_changes_nothing_of_the_owners(
    app: FastAPI, alice: TestClient, seed: Seed, intruder: tuple[TestClient, int]
) -> None:
    """After the whole sweep of writes against A's ids, A's course reads exactly as before."""
    client, own_course = intruder
    headers = {COURSE_HEADER: str(seed.course)}
    reads = [
        f"/api/courses/{seed.course}",
        f"/api/books/{seed.book}",
        f"/api/curriculum/versions/{seed.version}",
        f"/api/questions/{seed.question}",
        f"/api/custom-judges?curriculum_version_id={seed.version}",
        "/api/judge-prompts",
        "/api/question-sets",
        "/api/students",
        "/api/counts",
    ]
    before = [alice.get(url, headers=headers).json() for url in reads]

    for _, method, url, probe_headers, body, query in _probes(app, seed, own_course):
        client.request(method, url, headers=probe_headers, json=body, params=query)

    after = [alice.get(url, headers=headers).json() for url in reads]
    assert after == before


# ---------------------------------------------------------------- single gaps, by name


def test_course_creation_stamps_the_caller_and_ignores_a_posted_owner(
    app: FastAPI, seed: Seed, intruder: tuple[TestClient, int], session: Session
) -> None:
    client, _ = intruder
    alice_id = session.scalars(select(UserRow.id).where(UserRow.email == ALICE_EMAIL)).one()

    made = client.post("/api/courses", json={"name": "Mine", "owner_id": str(alice_id)})

    assert made.status_code == 201
    row = session.get(CourseRow, made.json()["id"])
    session.refresh(row)
    assert row.owner_id != alice_id
    assert client.get(f"/api/courses/{made.json()['id']}").status_code == 200


def test_the_prod_link_cannot_be_taken_over(
    app: FastAPI, seed: Seed, intruder: tuple[TestClient, int], session: Session
) -> None:
    """There is one prod alias per installation; A's link must keep serving A's set."""
    client, own_course = intruder
    # The intruder's course has a bank of its own, so a sync would otherwise go through.
    _content(session, own_course, label="Intruder")
    session.commit()

    response = client.post("/api/question-sets/prod/sync", headers={COURSE_HEADER: str(own_course)})

    assert response.status_code == 404, response.text
    assert client.get("/api/question-sets/prod").json()["id"] == seed.qset


def test_a_learner_reaches_only_their_own_run(app: FastAPI, seed: Seed) -> None:
    """The student flow is public, but a run answers only to its learner's token."""
    with TestClient(app) as browser:
        enrolled = browser.post(
            "/api/students", json={"display_name": "Mallory", "email": "m@example.edu"}
        ).json()
        browser.headers[STUDENT_HEADER] = enrolled["resume_token"]

        for method, url in [
            ("GET", f"/api/training-sessions/{seed.run}"),
            ("GET", f"/api/training-sessions/{seed.run}/next"),
            ("POST", f"/api/training-sessions/{seed.run}/live-question"),
            ("GET", f"/api/training-sessions/{seed.run}/progress"),
            ("POST", f"/api/training-sessions/{seed.run}/end"),
            ("GET", f"/api/attempts/{seed.attempt}"),
            ("GET", f"/api/attempts/{seed.attempt}/review"),
        ]:
            response = browser.request(method, url)
            assert response.status_code == 404, (url, response.text)
            _assert_private(response, url)
        started = browser.post(
            "/api/training-sessions",
            json={"student_id": seed.student, "set_version_id": seed.qset},
        )
        assert started.status_code == 404
        # Their own run on the same (public) classroom link works.
        own = browser.post(
            "/api/training-sessions",
            json={"student_id": enrolled["id"], "set_version_id": seed.qset},
        )
        assert own.status_code == 201, own.text
        assert browser.get(f"/api/training-sessions/{own.json()['id']}").status_code == 200


def test_a_new_accounts_first_login_lands_on_an_empty_working_studio(
    app: FastAPI, seed: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Studio's own first calls: who am I, my courses, the overview, then a new course."""
    _create_account(monkeypatch, "first-login@example.edu")
    with TestClient(app) as browser:
        assert browser.get("/api/auth/me").status_code == 401
        login = browser.post(
            "/api/auth/login",
            data={"username": "first-login@example.edu", "password": PASSWORD},
        )
        assert login.status_code == 204, login.text

        me = browser.get("/api/auth/me")
        assert me.status_code == 200 and me.json()["email"] == "first-login@example.edu"
        assert browser.get("/api/courses").json() == {"courses": []}
        assert browser.get("/api/courses/overview").json() == {"courses": [], "activity": []}

        course = browser.post("/api/courses", json={"name": "Physics 101"})
        assert course.status_code == 201, course.text
        course_id = course.json()["id"]
        overview = browser.get("/api/courses/overview").json()
        assert [entry["course"]["id"] for entry in overview["courses"]] == [course_id]
        assert overview["activity"] == []
        assert browser.get(f"/api/courses/{course_id}").status_code == 200
        counts = browser.get("/api/counts", headers={COURSE_HEADER: str(course_id)}).json()
        assert set(counts.values()) == {0}, counts
