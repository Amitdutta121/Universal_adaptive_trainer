"""Course design: curriculum plus the styles and recipes each subtopic uses (ADR-078). LLM faked."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.course_design import (
    DesignCatalogue,
    design_curriculum,
    get_design,
    require_complete,
    suggest_recipes,
    suggest_styles,
)
from app.course_design.design import ExistingItem
from app.curriculum.drafting import DraftBrief
from app.errors import DomainRuleError, NotFoundError
from app.persistence.database import get_session_factory
from app.persistence.models import CourseRow
from tests.agent_support import PROFESSOR_ID, result_of, run
from tests.test_tutorial_generator import QueuedClient

BRIEF = DraftBrief(title="Game AI", description="Search and decision making for game agents.")

CURRICULUM = {
    "analysis": "Search before decisions.",
    "label": "Game AI",
    "topics": [
        {
            "name": "Search",
            "subtopics": [
                {"name": "Breadth-first search", "description": "Expand nodes by depth."},
                {"name": "A* search", "description": "Order by cost plus heuristic."},
            ],
        },
        {"name": "Decisions", "subtopics": [{"name": "Finite state machines"}]},
    ],
    "out_of_scope": ["Live demos"],
}

CATALOGUE = DesignCatalogue(
    styles=(ExistingItem("py.concept_check", "Check one concept", "multiple_choice", "Pick."),),
    recipes=(ExistingItem("py.worked", "Worked example", "markdown", "Read it."),),
)

STYLE_PLAN = {
    "reasoning": "Tracing and choosing.",
    "styles": [
        {
            "key": "s1",
            "existing_id": "py.concept_check",
            "name": "Pick the right search",
            "question_type": "coding",
            "summary": "Choose the search that fits.",
        },
        {
            "key": "s2",
            "name": "Trace the search",
            "question_type": "output_prediction",
            "summary": "Give the visit order.",
        },
        # A type the app cannot mark: dropped.
        {
            "key": "s3",
            "name": "Explain in words",
            "question_type": "short_explanation",
            "summary": "Write a paragraph.",
        },
        # Never assigned: dropped.
        {"key": "s4", "name": "Unused", "question_type": "true_false", "summary": "-"},
    ],
    "assignments": [
        {"subtopic": "T1.S1", "styles": ["s2", "s3"]},
        {"subtopic": "T1.S2", "styles": ["s2", "s1"]},
        # T2.S1 missing: it gets the most-used style.
    ],
}
RECIPE_PLAN = {
    "reasoning": "Students step through searches.",
    "recipes": [
        {"key": "r1", "existing_id": "py.worked", "name": "", "form": "html", "summary": ""},
        {"key": "r2", "name": "Step-through grid", "form": "html", "summary": "Click through."},
        # A form the app does not have: dropped.
        {"key": "r3", "name": "3D scene", "form": "unity", "summary": "-"},
    ],
    "assignments": [
        {"subtopic": "T1.S1", "recipes": ["r2", "r3"]},
        {"subtopic": "T1.S2", "recipes": ["r2", "r1"]},
    ],
}  # fmt: skip


class Planners:
    """Answers each planner by the reply it asks for, so the two can run in parallel."""

    def __init__(self, styles=None, recipes=None) -> None:
        self.replies = {"_StylePlan": styles, "_RecipePlan": recipes}
        self.calls: dict[str, str] = {}
        self.lock = threading.Lock()

    def complete_structured(self, *, system, prompt, response_model, history=()):
        name = response_model.__name__
        with self.lock:
            self.calls[name] = prompt
        reply = self.replies[name]
        assert reply is not None, f"{name} was not expected"
        return response_model.model_validate(reply)


def _design(**overrides):
    """A whole design: the curriculum, then styles and recipes, as the agent runs the steps."""
    draft, plan = QueuedClient(CURRICULUM), Planners(STYLE_PLAN, RECIPE_PLAN)
    design = design_curriculum(
        course_id=overrides.pop("course_id", 5), brief=BRIEF, draft_client=draft
    )
    suggest_styles(design, CATALOGUE, client=plan)
    design = suggest_recipes(design, CATALOGUE, client=plan)
    return design, draft, plan


def test_a_design_keeps_only_what_the_app_can_make_and_serves_every_subtopic() -> None:
    design, _, plan = _design()

    assert [t.name for t in design.curriculum.topics] == ["Search", "Decisions"]
    assert design.out_of_scope == ["Live demos"]
    styles = {s.key: s for s in design.styles}
    assert set(styles) == {"s1", "s2"}
    # A reused style keeps its real type, shown under a name in this course's terms with the
    # name it was written under beside it.
    assert (styles["s1"].name, styles["s1"].original_name, styles["s1"].question_type) == (
        "Pick the right search",
        "Check one concept",
        "multiple_choice",
    )
    assert styles["s2"].existing_id is None and styles["s2"].original_name is None
    recipes = {r.key: r for r in design.recipes}
    assert set(recipes) == {"r1", "r2"}
    # A reused recipe the planner did not rename keeps its own name.
    assert (recipes["r1"].name, recipes["r1"].original_name) == ("Worked example", None)
    assert design.style_use["T1.S1"] == ["s2"]
    assert design.recipe_use["T1.S1"] == ["r2"]
    assert design.style_use["T2.S1"] == ["s2"]  # filled with the most used
    assert design.recipe_use["T2.S1"] == ["r2"]
    # Each suggester was asked within the boundary, with only its own existing items.
    style_prompt, recipe_prompt = plan.calls["_StylePlan"], plan.calls["_RecipePlan"]
    assert "Outside the boundary" in style_prompt and "py.concept_check" in style_prompt
    assert "py.worked" not in style_prompt and "py.worked" in recipe_prompt
    assert "T1.S2 A* search" in style_prompt and "T1.S2 A* search" in recipe_prompt


def test_suggesters_running_side_by_side_keep_each_others_work() -> None:
    design = design_curriculum(course_id=5, brief=BRIEF, draft_client=QueuedClient(CURRICULUM))
    both_started = threading.Barrier(2, timeout=5)

    class Waiting(Planners):
        def complete_structured(self, **kwargs):
            both_started.wait()  # each waits for the other: only passes if they overlap
            return super().complete_structured(**kwargs)

    plan = Waiting(STYLE_PLAN, RECIPE_PLAN)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(suggest_styles, design, CATALOGUE, client=plan),
            pool.submit(suggest_recipes, design, CATALOGUE, client=plan),
        ]
        for job in jobs:
            job.result()

    kept = get_design(design.id, 5)
    assert kept.style_use is not None and kept.recipe_use is not None
    require_complete(kept)


def test_revising_the_styles_keeps_the_rest_of_the_design() -> None:
    design, _, _ = _design()
    plan = Planners(styles=STYLE_PLAN)

    revised = suggest_styles(design, CATALOGUE, change="Use fewer styles", client=plan)

    assert list(plan.calls) == ["_StylePlan"]
    assert revised.id == design.id
    assert revised.curriculum == design.curriculum
    assert (revised.recipes, revised.recipe_use) == (design.recipes, design.recipe_use)
    prompt = plan.calls["_StylePlan"]
    assert "Use fewer styles" in prompt and "# Current styles" in prompt


def test_redrafting_the_curriculum_asks_for_styles_and_recipes_again() -> None:
    design, _, _ = _design()
    draft = QueuedClient(CURRICULUM)

    redrafted = design_curriculum(
        course_id=5, design=design, change="Merge the search topics", draft_client=draft
    )

    prompt = draft.calls[0]["prompt"]
    assert "# Current taxonomy" in prompt and "Merge the search topics" in prompt
    assert redrafted.id == design.id
    assert redrafted.style_use is None and redrafted.recipe_use is None
    assert redrafted.styles == design.styles  # kept, for the suggesters to revise
    with pytest.raises(DomainRuleError):
        require_complete(redrafted)


def test_a_design_is_only_found_in_its_own_course() -> None:
    design, _, _ = _design(course_id=5)
    with pytest.raises(NotFoundError):
        get_design(design.id, 6)


# -- The agent's tools --------------------------------------------------------------------------


@pytest.fixture
def db(client: TestClient) -> Iterator[None]:
    yield


def test_the_agent_builds_the_design_step_by_step_and_shows_it_by_name(db) -> None:
    with get_session_factory()() as session:
        course = CourseRow(name="Game AI", subject="custom", owner_id=PROFESSOR_ID,
                           question_types=["multiple_choice"])  # fmt: skip
        session.add(course)
        session.commit()
        course_id = course.id
    styles = {**STYLE_PLAN, "styles": STYLE_PLAN["styles"][1:2]}
    recipes = {**RECIPE_PLAN, "recipes": RECIPE_PLAN["recipes"][1:2]}

    started = result_of(
        run(
            ("design_curriculum", {"brief": BRIEF.model_dump()}),
            course_id=course_id,
            draft_client=QueuedClient(CURRICULUM),
        ).all_messages(),
        "design_curriculum",
    )
    assert (started.topic_count, started.subtopic_count) == (2, 3)
    assert (started.styles_ready, started.recipes_ready) == (False, False)

    ids = {"design_id": started.design_id}
    messages = run(
        ("suggest_styles", ids),
        ("suggest_recipes", ids),
        ("show_design", ids),
        course_id=course_id,
        setup_client=Planners(styles, recipes),
    ).all_messages()
    view = result_of(messages, "show_design")

    assert (view.styles_ready, view.recipes_ready) == (True, True)
    assert [(s.name, s.question_type, s.new, s.used_by) for s in view.styles] == [
        ("Trace the search", "Output prediction", True, 3)
    ]
    assert view.recipes[0].form == "Interactive page"
    assert view.topics[0].subtopics[1].styles == ["Trace the search"]
    assert view.out_of_scope == ["Live demos"]


def test_the_agent_is_told_to_plan_with_the_step_tools_and_show_the_card() -> None:
    from app.agent.agent import INSTRUCTIONS

    for name in ("design_curriculum", "suggest_styles", "suggest_recipes", "show_design"):
        assert name in INSTRUCTIONS
    assert "rarely accept the first design" in INSTRUCTIONS
    assert "repeat the card in text" in INSTRUCTIONS


# -- Approving a design in one step -------------------------------------------------------------


def test_approving_a_design_saves_curriculum_and_recipes_and_drafts_styles(db, monkeypatch) -> None:
    from app.course_design import approve
    from app.persistence.models import TutorialRecipeDecisionRow
    from app.styles.drafting import StyleDraftResult
    from app.styles.library import styles_for
    from app.styles.loader import parse_style_text
    from app.subjects import profile_for_course_id
    from tests.test_course_styles import _style_yaml
    from tests.test_experimental_recipes import DRAFT as RECIPE_DRAFT

    factory = get_session_factory()
    with factory() as session:
        course = CourseRow(name="Game AI", subject="intro_python", owner_id=PROFESSOR_ID)
        session.add(course)
        session.commit()
        course_id = course.id
    design, _, _ = _design(course_id=course_id)
    asked: list[str] = []

    def fake_draft_style(session, profile, client, description, current_yaml=None):
        asked.append(description)
        text = _style_yaml("py.trace_search")
        return StyleDraftResult(
            yaml=text, problems=[], style=parse_style_text(text, "intro_python", source="t")
        )

    monkeypatch.setattr(approve.style_drafting, "draft_style", fake_draft_style)
    recipe_client = QueuedClient(RECIPE_DRAFT)

    approved = approve.approve_design(
        design,
        session_factory=factory,
        style_client=QueuedClient(),
        recipe_client=recipe_client,
    )

    # The new style was drafted from what the professor saw, but not saved: it is offered for
    # review with its examples. The existing one is reused.
    assert asked == ["Trace the search: Give the visit order. Question type: output_prediction."]
    assert [(s.name, s.id, s.new) for s in approved.styles] == [
        ("Pick the right search", "py.concept_check", False),
        ("Trace the search", None, True),
    ]
    (offered,) = approved.style_drafts
    assert offered.style_id == "py.trace_search" and offered.style["examples"]
    with factory() as session:
        saved = styles_for(session, profile_for_course_id(session, course_id))
        assert "py.trace_search" not in {s.id for s in saved}
    assert "Step-through grid" in recipe_client.calls[0]["prompt"]
    assert [(r.id, r.new, r.problem) for r in approved.recipes] == [
        ("py.worked", False, None),
        ("exp.analogy_card", True, None),
    ]
    # Every subtopic carries its saved and pending style ids, under its saved subtopic id.
    assert [
        (s.name, s.style_ids, s.pending_style_ids, s.recipe_ids) for s in approved.subtopics
    ] == [
        ("Breadth-first search", [], ["py.trace_search"], ["exp.analogy_card"]),
        ("A* search", ["py.concept_check"], ["py.trace_search"], ["exp.analogy_card", "py.worked"]),
        ("Finite state machines", [], ["py.trace_search"], ["exp.analogy_card"]),
    ]
    # Both the reused and the new recipe are approved for the new curriculum.
    with factory() as session:
        decisions = {
            (d.curriculum_version_id, d.recipe_id, d.approved)
            for d in session.query(TutorialRecipeDecisionRow)
        }
        version = approved.curriculum_version_id
        assert decisions == {(version, "exp.analogy_card", True), (version, "py.worked", True)}


def test_a_new_style_whose_draft_fails_is_reported_not_offered(db, monkeypatch) -> None:
    from app.course_design import approve
    from app.styles.drafting import StyleDraftResult
    from tests.test_experimental_recipes import DRAFT as RECIPE_DRAFT

    factory = get_session_factory()
    with factory() as session:
        course = CourseRow(name="Game AI", subject="intro_python", owner_id=PROFESSOR_ID)
        session.add(course)
        session.commit()
        course_id = course.id
    design, _, _ = _design(course_id=course_id)
    monkeypatch.setattr(
        approve.style_drafting,
        "draft_style",
        lambda *a, **k: StyleDraftResult(yaml="", problems=["example 1 fails its grader"]),
    )

    approved = approve.approve_design(
        design,
        session_factory=factory,
        style_client=QueuedClient(),
        recipe_client=QueuedClient(RECIPE_DRAFT),
    )

    failed = next(s for s in approved.styles if s.new)
    assert (failed.id, failed.problem) == (None, "example 1 fails its grader")
    assert approved.style_drafts == []
    # The curriculum is still saved; subtopics keep only the styles that exist.
    assert approved.subtopics[1].style_ids == ["py.concept_check"]
    assert approved.subtopics[0].pending_style_ids == []


def test_approving_a_design_waits_for_the_professor() -> None:
    from app.agent.agent import INSTRUCTIONS
    from app.agent.approvals import APPROVAL_REQUIRED

    assert {"approve_course_design", "save_style"} <= APPROVAL_REQUIRED
    assert "save_style once for every entry of style_drafts" in INSTRUCTIONS
