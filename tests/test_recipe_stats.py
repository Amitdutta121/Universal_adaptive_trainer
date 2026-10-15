"""Per-recipe stats and how they steer the composer (Phase 6, Task 28)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_tutorial_serving import _course, _run

from app.domain.enums import Difficulty
from app.persistence.models import (
    CurriculumVersionRow,
    StudentAttemptRow,
    TopicRow,
    TutorialBlockViewRow,
)
from app.tutorials.approval import decide_recipe
from app.tutorials.stats import (
    MIN_DECISIONS,
    MIN_OUTCOMES,
    RecipeStats,
    recipe_stats,
    record_outcome,
)


def _views(session: Session) -> list[TutorialBlockViewRow]:
    session.expire_all()
    return list(session.scalars(select(TutorialBlockViewRow).order_by(TutorialBlockViewRow.id)))


def test_approval_rate_is_stored_per_recipe(session: Session) -> None:
    versions = []
    for n in range(3):
        version = CurriculumVersionRow(label=f"T{n}")
        version.topics.append(TopicRow(name="t"))
        session.add(version)
        versions.append(version)
    session.flush()
    for version, approved in zip(versions, (True, True, False), strict=True):
        decide_recipe(
            session, curriculum_version_id=version.id, recipe_id="py.topic_flow", approved=approved
        )
    session.commit()

    stats = recipe_stats(session, None)["py.topic_flow"]

    assert (stats.decided, stats.approved) == (3, 2)
    assert stats.approval_rate == 2 / 3


def test_next_attempt_correctness_is_stored_from_a_student_run(
    client: TestClient, session: Session
) -> None:
    set_id, subtopic_id = _course(session)
    served = client.get(f"/api/training-sessions/{_run(client, set_id)}/next").json()
    before = [v for v in _views(session) if v.moment == "before"]
    assert {v.block_id for v in before} == {b["id"] for b in served["preteach_blocks"]}
    assert all(v.next_correct is None for v in before)

    # Pre-teaching, then a wrong answer: its own pre-teaching gets the outcome.
    result = client.post(
        f"/api/attempts/{served['attempt_id']}/answer", json={"answer": "false"}
    ).json()
    views = _views(session)
    assert [v.next_correct for v in views if v.moment == "before"] == [False] * len(before)
    after = [v for v in views if v.moment == "after"]
    assert {v.block_id for v in after} == {b["id"] for b in result["tutorial_blocks"]}
    assert all(v.next_correct is None for v in after)

    # The next answer in the subtopic is right: that is the result-card blocks' outcome.
    first = session.get(StudentAttemptRow, served["attempt_id"])
    second = StudentAttemptRow(
        session_id=first.session_id,
        student_id=first.student_id,
        question_id=first.question_id,
        ordinal=2,
        subtopic_id=subtopic_id,
        requested_difficulty=Difficulty.EASY,
        served_difficulty=Difficulty.EASY,
        score=100.0,
    )
    session.add(second)
    session.flush()
    record_outcome(session, second, correct=True)
    session.commit()

    assert all(v.next_correct is True for v in _views(session) if v.moment == "after")
    stats = recipe_stats(session, None)
    assert sum(s.outcomes for s in stats.values()) == len(before) + len(after)
    listed = client.get("/api/tutorial-recipes").json()["stats"]
    assert set(listed) == set(stats)


def test_an_unknown_recipe_weighs_one() -> None:
    assert RecipeStats("r").weight == 1.0


def test_a_recipe_below_the_threshold_is_dropped_only_with_enough_evidence() -> None:
    assert RecipeStats("r", outcomes=MIN_OUTCOMES, next_correct=1).weight == 0.0
    assert RecipeStats("r", outcomes=4, next_correct=0).weight > 0.0
    assert RecipeStats("r", decided=MIN_DECISIONS, approved=0).weight == 0.0
    assert RecipeStats("r", decided=1, approved=0).weight > 0.0


def test_better_outcomes_weigh_more() -> None:
    good = RecipeStats("r", decided=4, approved=4, outcomes=30, next_correct=24)
    poor = RecipeStats("r", decided=4, approved=4, outcomes=30, next_correct=12)
    assert good.weight > poor.weight > 0
    assert RecipeStats("r", outcomes=30, next_correct=24).weight > RecipeStats("r").weight
