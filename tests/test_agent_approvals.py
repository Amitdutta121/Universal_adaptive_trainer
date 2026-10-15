"""The agent can't approve, publish or spend without the professor's click (Phase 8, Task 33).

"The click" is a ``DeferredToolResults`` approval in the next run, which is what the AG-UI
route builds from the chat panel's ``resume``. Each gated tool is run three ways: with no
click (the run stops and nothing is written), denied (nothing is written and the model is told)
and approved (the service runs). Spending is checked one step further: ``run_generation`` only
starts a run that ``plan_generation`` priced, at the call count it was priced at.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ToolReturnPart
from sqlalchemy import select

from app.agent.approvals import APPROVAL_REQUIRED, SignedPlan, open_plan, sign_plan
from app.agent.tools import (
    CurriculumTree,
    PricedPlan,
    PublishedSet,
    SavedStyle,
    StartedRun,
    ToolRefusal,
    toolset,
)
from app.errors import DomainRuleError
from app.persistence.database import get_session_factory
from app.persistence.models import (
    BackgroundJobRow,
    CourseRow,
    CourseStyleRow,
    CurriculumVersionRow,
    QuestionSetupRow,
    QuestionSetVersionRow,
    SubtopicRow,
)
from app.web.routes.api.agent import get_agent_model
from tests.agent_support import result_of, run, scripted, tool_returns
from tests.conftest import TEST_PROFESSOR_ID
from tests.test_agent_tools import DOCUMENT, _import_taxonomy
from tests.test_course_styles import _style_yaml
from tests.test_coverage import _question


@pytest.fixture
def db(client: TestClient) -> Iterator[None]:
    yield


class RecordingQueue:
    """Records submitted work without running it: these tests stop at "a run was queued"."""

    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, func, /, *args, **kwargs) -> None:
        self.submitted.append(func.__name__)


def _count(model) -> int:
    with get_session_factory()() as session:
        return len(session.scalars(select(model.id)).all())


def _python_course() -> int:
    with get_session_factory()() as session:
        course = CourseRow(name="Python", subject="intro_python", owner_id=TEST_PROFESSOR_ID)
        session.add(course)
        session.commit()
        return course.id


def _denied(result, tool_name: str) -> bool:
    return any(
        isinstance(part, ToolReturnPart)
        and part.tool_name == tool_name
        and "denied" in str(part.content).lower()
        for part in tool_returns(result.all_messages())
    )


def test_every_tool_that_writes_or_spends_waits_for_approval() -> None:
    gated = {name for name, tool in toolset.tools.items() if tool.requires_approval}
    assert gated == APPROVAL_REQUIRED
    # The read-only and free tools stay ungated.
    assert {"coverage_report", "plan_generation", "propose_curriculum"}.isdisjoint(gated)


# -- approve_curriculum ------------------------------------------------------------------------


def test_a_curriculum_is_not_saved_until_the_professor_approves_it(db) -> None:
    call = ("approve_curriculum", {"document": DOCUMENT})

    waiting = run(call)
    assert isinstance(waiting.output, DeferredToolRequests)
    (pending,) = waiting.output.approvals
    assert pending.tool_name == "approve_curriculum"
    assert pending.args_as_dict()["document"]["label"] == "Intro Python"
    assert _count(CurriculumVersionRow) == 0

    denied = run(call, decision=False)
    assert _denied(denied, "approve_curriculum")
    assert _count(CurriculumVersionRow) == 0

    approved = run(call, decision=True)
    saved = result_of(approved.all_messages(), "approve_curriculum")
    assert isinstance(saved, CurriculumTree)
    assert [t["name"] for t in saved.topics] == ["Loops", "Functions"]
    assert _count(CurriculumVersionRow) == 1


def test_an_edit_to_a_saved_curriculum_waits_for_approval(db) -> None:
    version_id = _import_taxonomy()
    with get_session_factory()() as session:
        version = session.get(CurriculumVersionRow, version_id)
        tree = {
            "label": "Renamed by the agent",
            "topics": [
                {
                    "id": t.id,
                    "name": t.name,
                    "subtopics": [{"id": s.id, "name": s.name} for s in t.subtopics],
                }
                for t in version.topics
            ],
        }
    call = ("edit_curriculum", {"version_id": version_id, "update": tree})

    assert isinstance(run(call).output, DeferredToolRequests)
    assert run(call, decision=False) is not None
    with get_session_factory()() as session:
        assert session.get(CurriculumVersionRow, version_id).label == "Intro Python"


# -- save_style --------------------------------------------------------------------------------


def test_a_style_is_not_saved_until_the_professor_approves_it(db) -> None:
    course = _python_course()
    call = ("save_style", {"yaml": _style_yaml()})

    assert isinstance(run(call, course_id=course).output, DeferredToolRequests)
    assert _denied(run(call, decision=False, course_id=course), "save_style")
    assert _count(CourseStyleRow) == 0

    saved = result_of(run(call, decision=True, course_id=course).all_messages(), "save_style")
    assert isinstance(saved, SavedStyle)
    assert saved.style_id == "py.my_output"
    assert _count(CourseStyleRow) == 1


# -- publish_set -------------------------------------------------------------------------------


def test_a_set_is_not_published_until_the_professor_approves_it(db) -> None:
    version_id = _import_taxonomy()
    with get_session_factory()() as session:
        version = session.get(CurriculumVersionRow, version_id)
        _question(session, version=version, subtopic_id=version.topics[0].subtopics[0].id)
    call = ("publish_set", {"curriculum_version_id": version_id})

    assert isinstance(run(call).output, DeferredToolRequests)
    assert _denied(run(call, decision=False), "publish_set")
    assert _count(QuestionSetVersionRow) == 0

    published = result_of(run(call, decision=True).all_messages(), "publish_set")
    assert isinstance(published, PublishedSet)
    assert published.join_path == f"/students/join?taxonomy={version_id}"
    assert _count(QuestionSetVersionRow) == 1


# -- plan_generation and run_generation --------------------------------------------------------


def _gaps_target() -> dict:
    _import_taxonomy()
    with get_session_factory()() as session:
        subtopic_id = session.scalars(select(SubtopicRow.id)).first()
    return {"kind": "gaps", "targets": [{"subtopic_id": subtopic_id, "difficulty": "easy"}]}


def _priced(target: dict, **deps) -> PricedPlan:
    plan = result_of(
        run(("plan_generation", {"target": target}), **deps).all_messages(), "plan_generation"
    )
    assert isinstance(plan, PricedPlan), plan
    return plan


def test_planning_is_free_and_queues_nothing(db) -> None:
    queue = RecordingQueue()
    plan = _priced(_gaps_target(), queue=queue)
    assert plan.plan.totals.questions_to_create == 1
    # One generation call plus one call per judge.
    assert plan.model_calls == plan.plan.totals.generation_calls + plan.plan.totals.judge_calls
    assert queue.submitted == []
    assert _count(BackgroundJobRow) == 0


def test_a_priced_run_starts_only_when_the_professor_approves_it(db) -> None:
    queue = RecordingQueue()
    plan = _priced(_gaps_target(), queue=queue)
    call = ("run_generation", {"plan_id": plan.plan_id, "model_calls": plan.model_calls})
    embedder = lambda: None  # noqa: E731 - the job is recorded, never run

    waiting = run(call, queue=queue, embedder=embedder)
    assert isinstance(waiting.output, DeferredToolRequests)
    assert waiting.output.approvals[0].args_as_dict()["model_calls"] == plan.model_calls
    assert _denied(run(call, decision=False, queue=queue, embedder=embedder), "run_generation")
    assert queue.submitted == [] and _count(BackgroundJobRow) == 0

    started = result_of(
        run(call, decision=True, queue=queue, embedder=embedder).all_messages(), "run_generation"
    )
    assert isinstance(started, StartedRun)
    assert started.kind == "gaps"
    assert queue.submitted == ["run_coverage_fill"]
    assert _count(BackgroundJobRow) == 1


def test_a_new_setup_is_priced_then_saved_with_its_first_round_only_on_approval(db) -> None:
    version_id = _import_taxonomy()
    with get_session_factory()() as session:
        subtopic_ids = list(session.scalars(select(SubtopicRow.id)))
    target = {
        "kind": "new_setup",
        "curriculum_version_id": version_id,
        "approved_styles": [
            {"subtopic_id": s, "style_ids": ["py.predict_output"]} for s in subtopic_ids
        ],
        "cell_targets": [
            {"subtopic_id": s, "difficulty": "easy", "target": 2} for s in subtopic_ids
        ],
        "round_size": 2,
    }
    queue = RecordingQueue()
    plan = _priced(target, queue=queue)
    assert plan.plan.totals.questions_to_create == 2
    assert plan.model_calls == 2  # a round's judges run inside its retry loop
    call = ("run_generation", {"plan_id": plan.plan_id, "model_calls": plan.model_calls})

    assert isinstance(run(call, queue=queue).output, DeferredToolRequests)
    assert _count(QuestionSetupRow) == 0 and queue.submitted == []

    started = result_of(run(call, decision=True, queue=queue).all_messages(), "run_generation")
    assert isinstance(started, StartedRun), started
    assert started.kind == "new_setup" and started.job_id.startswith("round-")
    assert _count(QuestionSetupRow) == 1
    assert queue.submitted == ["run_round"]


@pytest.mark.parametrize("tamper", ["calls", "plan_id", "unplanned"])
def test_an_approved_run_that_is_not_the_priced_plan_is_refused(db, tamper: str) -> None:
    queue = RecordingQueue()
    target = _gaps_target()
    plan = _priced(target, queue=queue)
    args = {"plan_id": plan.plan_id, "model_calls": plan.model_calls}
    if tamper == "calls":
        args["model_calls"] = 1
    elif tamper == "plan_id":
        # The same target with a bigger price, without the server's signature.
        expires, _, signature = plan.plan_id.split(".")
        forged = SignedPlan(course_id=None, target=target, model_calls=1).model_dump_json()
        payload = base64.urlsafe_b64encode(forged.encode()).decode()
        args = {"plan_id": f"{expires}.{payload}.{signature}", "model_calls": 1}
    else:
        args["plan_id"] = "not-a-plan"

    result = run(("run_generation", args), decision=True, queue=queue, embedder=lambda: None)
    assert isinstance(result_of(result.all_messages(), "run_generation"), ToolRefusal)
    assert queue.submitted == [] and _count(BackgroundJobRow) == 0


def test_a_plan_is_bound_to_its_course_and_expires() -> None:
    plan_id = sign_plan(SignedPlan(course_id=1, target={"kind": "gaps"}, model_calls=7), now=1000)
    assert open_plan(plan_id, course_id=1, model_calls=7, now=1001).model_calls == 7
    with pytest.raises(DomainRuleError, match="another course"):
        open_plan(plan_id, course_id=2, model_calls=7, now=1001)
    with pytest.raises(DomainRuleError, match="expired"):
        open_plan(plan_id, course_id=1, model_calls=7, now=1000 + 31 * 60)


# -- the same through the AG-UI route ----------------------------------------------------------


def _events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def _agent_request(client: TestClient, **body) -> list[dict]:
    payload = {
        "threadId": "t1",
        "runId": body.pop("runId", "r1"),
        "state": None,
        "tools": [],
        "context": [],
        "forwardedProps": None,
        **body,
    }
    response = client.post("/api/agent", json=payload, headers={"Accept": "text/event-stream"})
    assert response.status_code == 200, response.text
    events = _events(response.text)
    assert not [e for e in events if e["type"] == "RUN_ERROR"], events
    return events


@pytest.mark.parametrize(
    ("payload", "saved"),
    [({"approved": True}, 1), ({"approved": False}, 0), ({"approved": "true"}, 0), ({}, 0)],
)
def test_over_ag_ui_only_the_resume_click_approves(
    client: TestClient, configured_app: FastAPI, payload: dict, saved: int
) -> None:
    configured_app.dependency_overrides[get_agent_model] = lambda: scripted(
        ("approve_curriculum", {"document": DOCUMENT}), final="Saved."
    )
    user = {"id": "m1", "role": "user", "content": "Approve this curriculum."}
    first = _agent_request(client, messages=[user])
    finished = first[-1]
    assert finished["type"] == "RUN_FINISHED"
    (interrupt,) = finished["outcome"]["interrupts"]
    assert _count(CurriculumVersionRow) == 0

    call = next(e for e in first if e["type"] == "TOOL_CALL_START")
    assistant = {
        "id": "m2",
        "role": "assistant",
        "toolCalls": [
            {
                "id": call["toolCallId"],
                "type": "function",
                "function": {
                    "name": "approve_curriculum",
                    "arguments": json.dumps({"document": DOCUMENT}),
                },
            }
        ],
    }
    _agent_request(
        client,
        runId="r2",
        messages=[user, assistant],
        resume=[{"interruptId": interrupt["id"], "status": "resolved", "payload": payload}],
    )
    assert _count(CurriculumVersionRow) == saved
