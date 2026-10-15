"""The professor agent's tools (Phase 8, Tasks 32 and 34).

The agent runs on a scripted fake model (``tests/agent_support.py``) against the test
database, so each test checks that a tool reaches the same service a Studio route uses and
that the app's refusals reach the model as data, not as a crash.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import get_args

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_ai.messages import ModelRequest, RetryPromptPart
from sqlalchemy import select

from app.agent.agent import agent_model
from app.agent.tools import (
    VIEW_PATHS,
    ClassReport,
    CourseOverview,
    CoverageSummary,
    CurriculumProposal,
    CurriculumTree,
    OpenedView,
    ReviewSummary,
    StudentReport,
    StylePreview,
    ToolRefusal,
    View,
)
from app.config import LLMProvider, Settings
from app.curriculum import TaxonomyImportService
from app.domain.enums import QuestionStatus
from app.errors import ConfigurationError
from app.persistence.database import get_session_factory
from app.persistence.models import BookRow, CourseRow, CurriculumVersionRow
from app.styles.schema import SetupSuggestion
from app.web.routes.api.agent import get_agent_model
from tests.agent_support import result_of, run, scripted
from tests.test_coverage import _question
from tests.test_styles import FakeSuggester
from tests.test_taxonomy_drafting import _FakeDrafter
from tests.test_youtube_source import URL, Fakes

DOCUMENT = {
    "schema_version": "1",
    "label": "Intro Python",
    "topics": [
        {"name": "Loops", "subtopics": [{"name": "for loops"}, {"name": "while loops"}]},
        {"name": "Functions", "subtopics": [{"name": "Defining"}]},
    ],
}


@pytest.fixture
def db(client: TestClient) -> Iterator[None]:
    """The app's schema, created by the client's lifespan; tools open their own sessions."""
    yield


def _import_taxonomy(course_id: int | None = None) -> int:
    with get_session_factory()() as session:
        version = TaxonomyImportService(session).import_upload(
            filename="taxonomy.json",
            data=json.dumps(DOCUMENT).encode("utf-8"),
            course_id=course_id,
        )
        session.commit()
        return version.id


def _course(name: str) -> int:
    with get_session_factory()() as session:
        course = CourseRow(name=name)
        session.add(course)
        session.commit()
        return course.id


def _run(*calls: tuple[str, dict], **deps_overrides):
    """Run ``calls``, with the professor approving any that wait for approval."""
    return run(*calls, decision=True, **deps_overrides).all_messages()


# -- import_material ---------------------------------------------------------------------------


def test_import_material_imports_a_youtube_video_through_the_import_service(db) -> None:
    fakes = Fakes()
    messages = _run(
        ("import_material", {"url": URL}),
        youtube_fetch=fakes.fetch,
        youtube_check=fakes.check,
    )
    imported = result_of(messages, "import_material")
    assert imported.title == "Loops in Python"
    with get_session_factory()() as session:
        assert session.get(BookRow, imported.book_id) is not None


def test_import_material_returns_the_refusal_for_a_link_that_is_not_youtube(db) -> None:
    fakes = Fakes()
    messages = _run(
        ("import_material", {"url": "https://vimeo.com/12345"}),
        youtube_fetch=fakes.fetch,
        youtube_check=fakes.check,
    )
    refusal = result_of(messages, "import_material")
    assert isinstance(refusal, ToolRefusal)
    assert fakes.fetched == []
    with get_session_factory()() as session:
        assert session.scalars(select(BookRow)).all() == []


# -- propose_curriculum ------------------------------------------------------------------------


def test_propose_curriculum_drafts_through_the_drafting_service_and_saves_nothing(db) -> None:
    drafter = _FakeDrafter()
    messages = _run(
        ("propose_curriculum", {"brief": {"title": "Intro Biology", "description": "Cells."}}),
        draft_client=drafter,
    )
    proposal = result_of(messages, "propose_curriculum")
    assert isinstance(proposal, CurriculumProposal)
    assert proposal.drafted_by == "fake/taxonomy-drafter"
    # The repair step of the real service ran: the near-duplicate and the empty topic are gone.
    assert [t["name"] for t in proposal.document["topics"]] == ["Cells"]
    assert len(proposal.document["topics"][0]["subtopics"]) == 2
    assert "Intro Biology" in drafter.calls[0][1]
    with get_session_factory()() as session:
        assert session.scalars(select(CurriculumVersionRow)).all() == []


# -- edit_curriculum ---------------------------------------------------------------------------


def _tree_of(version_id: int) -> dict:
    with get_session_factory()() as session:
        version = session.get(CurriculumVersionRow, version_id)
        return {
            "label": version.label,
            "topics": [
                {
                    "id": topic.id,
                    "name": topic.name,
                    "subtopics": [{"id": s.id, "name": s.name} for s in topic.subtopics],
                }
                for topic in version.topics
            ],
        }


def test_edit_curriculum_applies_the_tree_through_the_tree_service(db) -> None:
    version_id = _import_taxonomy()
    tree = _tree_of(version_id)
    tree["topics"][0]["subtopics"][0]["name"] = "for loops over lists"
    messages = _run(("edit_curriculum", {"version_id": version_id, "update": tree}))
    edited = result_of(messages, "edit_curriculum")
    assert isinstance(edited, CurriculumTree)
    assert edited.topics[0]["subtopics"][0]["name"] == "for loops over lists"
    assert _tree_of(version_id)["topics"][0]["subtopics"][0]["name"] == "for loops over lists"


def test_edit_curriculum_cannot_reach_a_version_in_another_course(db) -> None:
    mine, other = _course("Mine"), _course("Other")
    version_id = _import_taxonomy(course_id=other)
    tree = _tree_of(version_id)
    tree["label"] = "Taken over"
    messages = _run(("edit_curriculum", {"version_id": version_id, "update": tree}), course_id=mine)
    refusal = result_of(messages, "edit_curriculum")
    assert isinstance(refusal, ToolRefusal)
    assert "does not exist" in refusal.error
    assert _tree_of(version_id)["label"] == "Intro Python"


def test_a_malformed_tree_is_sent_back_to_the_model_rather_than_applied(db) -> None:
    version_id = _import_taxonomy()
    tree = _tree_of(version_id)
    tree["topics"].append(dict(tree["topics"][0], id=None))  # a duplicate topic name
    messages = _run(("edit_curriculum", {"version_id": version_id, "update": tree}))
    refusal = result_of(messages, "edit_curriculum")
    assert isinstance(refusal, ToolRefusal)
    assert len(_tree_of(version_id)["topics"]) == 2


# -- coverage_report ---------------------------------------------------------------------------


def test_coverage_report_lists_every_cell_still_owed_questions(db) -> None:
    _import_taxonomy()
    messages = _run(("coverage_report", {}))
    report = result_of(messages, "coverage_report")
    assert isinstance(report, CoverageSummary)
    assert report.curriculum_label == "Intro Python"
    assert report.question_count == 0
    assert not report.is_servable
    # Three subtopics x three difficulties, all empty.
    assert len(report.gaps) == report.total_cells == 9
    assert {gap.subtopic for gap in report.gaps} == {"for loops", "while loops", "Defining"}


# -- the model and the route -------------------------------------------------------------------


def test_the_agent_model_follows_the_agent_role_settings(settings: Settings) -> None:
    with pytest.raises(ConfigurationError):
        agent_model(settings)
    configured = settings.model_copy(
        update={
            "llm_provider": LLMProvider.OPENROUTER,
            "llm_api_key": SecretStr("sk-test"),
            "llm_model": "x/agent-1",
        }
    )
    model = agent_model(configured)
    assert model.model_name == "x/agent-1"
    assert "openrouter.ai" in str(model.base_url)


def _sse_events(body: str) -> list[dict]:
    return [
        json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")
    ]


def test_the_ag_ui_route_runs_the_agent_with_its_tools(
    client: TestClient, configured_app: FastAPI
) -> None:
    _import_taxonomy()
    configured_app.dependency_overrides[get_agent_model] = lambda: scripted(
        ("coverage_report", {}), final="Nine cells are empty."
    )
    response = client.post(
        "/api/agent",
        json={
            "threadId": "t1",
            "runId": "r1",
            "state": None,
            "messages": [{"id": "m1", "role": "user", "content": "How is coverage?"}],
            "tools": [],
            "context": [],
            "forwardedProps": None,
        },
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200, response.text
    events = _sse_events(response.text)
    assert not [e for e in events if e["type"] == "RUN_ERROR"], events
    types = [event["type"] for event in events]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    assert any(
        e["type"] == "TOOL_CALL_START" and e["toolCallName"] == "coverage_report" for e in events
    )
    assert "Nine cells are empty." in "".join(
        e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT"
    )


# -- Task 34: course_overview, preview_styles, suggest_setup, review_summary, student_report,
# -- open_view ---------------------------------------------------------------------------------


def test_course_overview_lists_the_ids_the_other_tools_take(db) -> None:
    version_id = _import_taxonomy()
    overview = result_of(_run(("course_overview", {})), "course_overview")
    assert isinstance(overview, CourseOverview)
    assert overview.approved_curriculum_version_id == version_id
    assert overview.curriculum_versions[0] == {
        "id": version_id,
        "label": "Intro Python",
        "status": "approved",
        "subtopics": 3,
    }
    assert overview.books == []


def test_preview_styles_without_ids_lists_the_course_library(db) -> None:
    preview = result_of(_run(("preview_styles", {})), "preview_styles")
    assert isinstance(preview, StylePreview)
    assert len(preview.styles) == 10
    assert "examples" not in preview.styles[0]


def test_preview_styles_puts_up_to_three_styles_side_by_side_with_their_samples(db) -> None:
    ids = ["py.predict_output", "py.fix_one_bug"]
    preview = result_of(_run(("preview_styles", {"style_ids": ids})), "preview_styles")
    assert [style["id"] for style in preview.styles] == ids
    assert all(len(style["examples"]) == 2 for style in preview.styles)

    unknown = result_of(_run(("preview_styles", {"style_ids": ["py.nope"]})), "preview_styles")
    assert isinstance(unknown, ToolRefusal)


def test_preview_styles_refuses_more_than_three_as_a_retry_to_the_model(db) -> None:
    four = ["py.predict_output", "py.fix_one_bug", "py.write_function", "py.order_lines"]
    messages = _run(("preview_styles", {"style_ids": four}))
    retries = [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]
    assert retries and retries[0].tool_name == "preview_styles"


def test_suggest_setup_runs_the_setup_suggester_and_saves_nothing(db) -> None:
    version_id = _import_taxonomy()
    with get_session_factory()() as session:
        subtopic_id = session.get(CurriculumVersionRow, version_id).topics[0].subtopics[0].id
    fake = FakeSuggester(
        {
            "subtopics": [
                {"subtopic_id": subtopic_id, "style_ids": ["py.predict_output"], "reason": "r"}
            ]
        }
    )
    suggestion = result_of(
        _run(("suggest_setup", {"curriculum_version_id": version_id}), setup_client=fake),
        "suggest_setup",
    )
    assert isinstance(suggestion, SetupSuggestion)
    assert len(fake.calls) == 1
    # Every subtopic gets styles and every cell a target, as from POST /setup/suggest.
    assert len(suggestion.subtopics) == 3 and len(suggestion.cell_targets) == 9


def test_review_summary_matches_the_review_queue_route(client: TestClient) -> None:
    version_id = _import_taxonomy()
    with get_session_factory()() as session:
        version = session.get(CurriculumVersionRow, version_id)
        _question(
            session,
            version=version,
            subtopic_id=version.topics[0].subtopics[0].id,
            status=QuestionStatus.VALIDATION_PASSED,
        )
    summary = result_of(_run(("review_summary", {})), "review_summary")
    route = client.get("/api/questions/review-queue").json()
    assert isinstance(summary, ReviewSummary)
    assert (summary.total, summary.reviewed, summary.remaining) == (
        route["total"],
        route["reviewed"],
        route["remaining"],
    )
    expected = route["question"]["question"]["id"] if route["question"] else None
    assert summary.next_question_id == expected


def test_student_report_gives_the_class_summary_or_one_student(client: TestClient) -> None:
    report = result_of(_run(("student_report", {})), "student_report")
    assert isinstance(report, ClassReport)
    assert report.student_count == 0 and report.weakest_subtopics == []

    created = client.post("/api/students", json={"display_name": "Ada", "email": "ada@example.com"})
    assert created.status_code == 201, created.text
    student_id = created.json()["id"]
    one = result_of(_run(("student_report", {"student_id": student_id})), "student_report")
    assert isinstance(one, StudentReport)
    assert (one.name, one.answered, one.topics) == ("Ada", 0, [])

    missing = result_of(_run(("student_report", {"student_id": 999_999})), "student_report")
    assert isinstance(missing, ToolRefusal)


def test_open_view_returns_the_studio_path_inside_the_course(db) -> None:
    version_id = _import_taxonomy()

    def opened(args: dict):
        return result_of(_run(("open_view", args)), "open_view")

    assert opened({"view": "coverage"}) == OpenedView(view="coverage", path="/coverage")
    assert opened({"view": "curriculum_version", "id": version_id}).path == (
        f"/curriculum/versions/{version_id}"
    )
    assert isinstance(opened({"view": "book"}), ToolRefusal)  # needs an id
    assert isinstance(opened({"view": "book", "id": 999_999}), ToolRefusal)
    assert isinstance(opened({"view": "subtopic", "id": 999_999}), ToolRefusal)


def test_open_view_cannot_open_a_row_of_another_course(db) -> None:
    mine, other = _course("Mine"), _course("Other")
    version_id = _import_taxonomy(course_id=other)
    refusal = result_of(
        _run(("open_view", {"view": "curriculum_version", "id": version_id}), course_id=mine),
        "open_view",
    )
    assert isinstance(refusal, ToolRefusal)


def test_every_view_has_a_studio_page() -> None:
    pages = Path(__file__).parents[1] / "frontend" / "src" / "app" / "courses" / "[courseId]"
    assert set(VIEW_PATHS) == set(get_args(View))
    for path in VIEW_PATHS.values():
        folder = path.strip("/").replace("{id}", "*")
        assert list(pages.glob(f"{folder}/page.tsx")), path
