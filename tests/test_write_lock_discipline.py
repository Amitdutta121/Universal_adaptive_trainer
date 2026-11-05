"""Generation jobs must not hold the database write lock across an LLM or embedder call.

SQLite has one writer at a time. A job that writes (even a cache row) and then waits on a
model keeps every professor review and student answer waiting until it commits; past the
busy timeout those requests fail with ``database is locked`` (TASK-140). Each probe below
tries to take the write lock from a second connection at the moment of a model call.
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Sequence
from typing import Any

import pytest
from llm_fakes import MetricJudgeClient
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from test_live_questions import _answer_everything, live_enabled  # noqa: F401
from test_rounds import (  # noqa: F401  (fixtures are used by name)
    STYLE_A,
    KeywordEmbedder,
    _mcq,
    _professor_approved,
    _question,
    _round,
    _run,
    _setup,
    env,
    fake_library,
)

from app.domain.enums import Difficulty, QuestionStatus, QuestionType, RoundStatus
from app.generation import live
from app.generation.rounds import start_round
from app.persistence.models import LiveQuestionJobRow
from app.persistence.repositories import (
    QuestionSetRepository,
    StudentRepository,
    TrainingSessionRepository,
)


class LockProbe:
    """Records every model call made while another connection holds the write lock."""

    def __init__(self, engine: Engine) -> None:
        self.path = engine.url.database
        self.calls = 0
        self.blocked: list[str] = []

    def check(self, what: str) -> None:
        self.calls += 1
        probe = sqlite3.connect(self.path, timeout=0.05, isolation_level=None)
        try:
            probe.execute("BEGIN IMMEDIATE")
            probe.execute("ROLLBACK")
        except sqlite3.OperationalError:
            self.blocked.append(what)
        finally:
            probe.close()


class ProbedClient(MetricJudgeClient):
    def __init__(self, probe: LockProbe, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.probe = probe

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        self.probe.check(f"llm:{response_model.__name__}")
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kwargs
        )


class ProbedEmbedder(KeywordEmbedder):
    def __init__(self, probe: LockProbe) -> None:
        self.probe = probe

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.probe.check("embed")
        return super().embed(texts)


def test_a_round_holds_no_write_lock_during_model_calls(
    session: Session,
    engine: Engine,
    env,  # noqa: F811
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "medium", 6)])
    # Approved questions with no cached vector: example retrieval and the duplicate check
    # embed them, which is where cache rows used to be written mid-generation.
    for prompt in ("Accepted: what does a while loop do?", "Accepted: when does a loop stop?"):
        _professor_approved(
            session,
            _question(
                session,
                env,
                env.while_loops,
                "medium",
                QuestionStatus.APPROVED,
                prompt=prompt,
                question_type=QuestionType.MULTIPLE_CHOICE,
            ),
        )
    row = start_round(session, setup.id, size=3, rng=random.Random(1))
    session.commit()
    probe = LockProbe(engine)
    client = ProbedClient(
        probe,
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
        difficulty=Difficulty.MEDIUM,
    )

    _run(engine, row.id, client, ProbedEmbedder(probe))

    assert _round(engine, row.id).status is RoundStatus.DONE
    assert probe.calls > 0
    assert probe.blocked == []


@pytest.mark.parametrize("difficulty", ["medium", "hard"])
def test_a_live_job_holds_no_write_lock_during_model_calls(
    session: Session,
    engine: Engine,
    env,  # noqa: F811
    difficulty: str,
) -> None:
    _setup(
        session,
        env,
        [(env.while_loops.id, difficulty, 1)],
        styles={env.while_loops.id: [STYLE_A.id]},
    )
    accepted = _question(
        session,
        env,
        env.while_loops,
        difficulty,
        QuestionStatus.APPROVED,
        prompt="Accepted: what does a while loop do?",
        question_type=QuestionType.MULTIPLE_CHOICE,
    )
    # Markable, so the student can answer it and the bank runs dry.
    accepted.content = _mcq(env.while_loops.topic_id, env.while_loops.id).model_dump(mode="json")
    session.commit()
    _professor_approved(session, accepted)
    student = StudentRepository(session).add("Grace")
    classroom = QuestionSetRepository(session).create(
        label="Live", question_ids=[], curriculum_version_id=env.version.id
    )
    classroom.notes = "Behind this taxonomy's classroom link"
    run = TrainingSessionRepository(session).create(
        student_id=student.id, set_version_id=classroom.id, rng_seed=3
    )
    session.commit()
    _answer_everything(session, run.id)
    job = live.next_for_session(session, run.id)
    session.commit()
    assert isinstance(job, LiveQuestionJobRow)
    probe = LockProbe(engine)
    # "hard" exercises the fallback that lowers the job's difficulty before generating.
    client = ProbedClient(
        probe,
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
        difficulty=Difficulty(job.difficulty),
        should_have_generated=False,
    )

    live.run_live_job(
        job.id,
        client=client,  # type: ignore[arg-type]
        embedder=ProbedEmbedder(probe),  # type: ignore[arg-type]
        session_factory=lambda: Session(engine, expire_on_commit=False),
    )

    assert probe.calls > 0
    assert probe.blocked == []


def test_a_locked_database_is_a_retryable_503_not_an_unknown_500(configured_app) -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    def locked() -> None:
        raise OperationalError(
            "UPDATE questions", {}, sqlite3.OperationalError("database is locked")
        )

    def broken() -> None:
        raise OperationalError("SELECT", {}, sqlite3.OperationalError("no such table: nope"))

    configured_app.add_api_route("/__locked", locked)
    configured_app.add_api_route("/__broken", broken)
    with TestClient(configured_app, raise_server_exceptions=False) as http:
        busy = http.get("/__locked")
        other = http.get("/__broken")

    assert busy.status_code == 503
    assert busy.json()["error"]["code"] == "database_busy"
    assert busy.headers["retry-after"] == "2"
    assert other.status_code == 500
    assert other.json()["error"]["code"] == "internal_error"
