"""Facets per subtopic (ADR-063 point 6, m7): listed once, one per target, saturation."""

from __future__ import annotations

from types import SimpleNamespace

from llm_fakes import MetricJudgeClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionStatus, RoundStatus
from app.generation.facets import facets_for
from app.generation.prompts import render_round_target
from app.generation.rounds import assign_facets, next_round, plan_targets
from app.generation.spec import require_approved_version
from app.persistence.models import GenerationRoundRow, QuestionRow, SubtopicFacetRow, SubtopicRow
from tests import test_rounds
from tests.test_rounds import _mcq, _queue, _round, _round_questions, _run, _setup, _target

env = test_rounds.env
fake_library = test_rounds.fake_library

FACETS = ["loop condition", "infinite loops", "loop counters", "break and continue"]


def _client(env: SimpleNamespace, facets: list[str] = FACETS) -> MetricJudgeClient:
    return MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
        difficulty=Difficulty.MEDIUM,
        facets=facets,
    )


def _covering(session: Session, env: SimpleNamespace, facet: str) -> QuestionRow:
    """An approved question of the while-loops medium cell that assesses ``facet``."""
    row = QuestionRow(
        curriculum_version_id=env.version.id,
        topic_id=env.while_loops.topic_id,
        subtopic_ids=[env.while_loops.id],
        difficulty=Difficulty.MEDIUM,
        status=QuestionStatus.APPROVED,
        prompt=f"About {facet}?",
        spec={"facet": facet},
    )
    session.add(row)
    session.commit()
    return row


def _list_facets(session: Session, env: SimpleNamespace) -> None:
    facets_for(session, env.while_loops, "Loops", client=_client(env))
    session.commit()


def test_facets_are_listed_once_per_subtopic_and_reused(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "medium", 5)])
    client = _client(env)

    first = _queue(session, setup, [_target(env)])
    _run(engine, first.id, client)
    second = GenerationRoundRow(setup_id=setup.id, number=2, targets=[_target(env)], requested=1)
    session.add(second)
    session.commit()
    _run(engine, second.id, client)

    assert client.facet_calls == 1
    stored = session.scalars(select(SubtopicFacetRow)).all()
    assert [(row.subtopic_id, row.facets) for row in stored] == [(env.while_loops.id, FACETS)]
    # The second round's target took the next facet: the first one is covered.
    (q1,) = _round_questions(engine, first.id)
    (q2,) = _round_questions(engine, second.id)
    assert (q1.spec["facet"], q2.spec["facet"]) == ("loop condition", "infinite loops")
    # A retry carries the original request as the conversation's first turn.
    last = client.generation_calls[-1]
    asked = last["history"][0][1] if last["history"] else last["prompt"]
    assert "Assess this facet of the subtopic: infinite loops." in asked


def test_two_targets_of_one_cell_never_share_a_facet(
    session: Session, env: SimpleNamespace
) -> None:
    _covering(session, env, "loop condition")
    version = require_approved_version(session, env.version.id)
    targets = [_target(env), _target(env), _target(env, difficulty="easy")]

    facets, saturated = assign_facets(session, version, targets, client=_client(env))

    assert facets == ["infinite loops", "loop counters", "loop condition"]
    assert saturated == []


def test_a_failure_to_list_facets_leaves_targets_without_one(
    session: Session, env: SimpleNamespace
) -> None:
    class Broken:
        description = "fake/broken"

        def complete_structured(self, **_kwargs):
            raise RuntimeError("provider down")

    version = require_approved_version(session, env.version.id)

    facets, saturated = assign_facets(session, version, [_target(env)], client=Broken())

    assert (facets, saturated) == ([None], [])
    assert session.scalar(select(func.count()).select_from(SubtopicFacetRow)) == 0


def test_a_saturated_cell_gets_no_target_and_the_round_names_it(
    session: Session, env: SimpleNamespace
) -> None:
    _list_facets(session, env)
    for facet in FACETS:
        _covering(session, env, facet)
    setup = _setup(session, env, [(env.while_loops.id, "medium", 5), (env.slicing.id, "medium", 1)])

    saturated: list = []
    targets = plan_targets(session, setup, size=10, saturated=saturated)
    row = next_round(session, setup.id)

    assert {target["subtopic_id"] for target in targets} == {env.slicing.id}
    assert saturated == [(env.while_loops.id, Difficulty.MEDIUM)]
    assert row.saturated == "While loops (medium)"
    assert all(target["subtopic_id"] == env.slicing.id for target in row.targets)


def test_a_cell_gets_no_more_targets_than_open_facets(
    session: Session, env: SimpleNamespace
) -> None:
    _list_facets(session, env)
    for facet in FACETS[:3]:
        _covering(session, env, facet)
    setup = _setup(session, env, [(env.while_loops.id, "medium", 10)])

    targets = plan_targets(session, setup, size=10)

    assert len(targets) == 1


def test_a_cell_found_saturated_while_running_is_skipped_and_named(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    """Facets listed for the first time by the round itself, all already covered."""
    for facet in FACETS:
        _covering(session, env, facet)
    setup = _setup(session, env, [(env.while_loops.id, "medium", 10)])
    row = _queue(session, setup, [_target(env)])
    client = _client(env)

    _run(engine, row.id, client)

    done = _round(engine, row.id)
    assert (done.status, done.produced, done.skipped) == (RoundStatus.DONE, 0, 1)
    assert done.saturated == "While loops (medium)"
    assert client.generation_calls == []


def test_the_target_block_names_the_facet() -> None:
    block = render_round_target(
        subtopic=SubtopicRow(id=7, name="While loops"),
        topic_name="Loops",
        style=None,
        facet="infinite loops",
    )
    assert (
        "Assess this facet of the subtopic: infinite loops. Other questions cover its other facets."
    ) in block
    bare = render_round_target(
        subtopic=SubtopicRow(id=7, name="While loops"), topic_name="Loops", style=None
    )
    assert "facet" not in bare
