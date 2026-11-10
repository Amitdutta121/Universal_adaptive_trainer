"""fig4: computed figures -- a program makes K copies of a question (ADR-080 point 3).

docs/FIGURE_QUESTIONS_MILESTONES.md, fig4. The model is faked; the programs really run, through
the local executor, so a crash, bad output or a slow run is the real thing. A rejected program
stores nothing, so nothing can be served from it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from alembic import command
from fastapi.testclient import TestClient
from llm_fakes import MetricJudgeClient, SequencedDraftClient
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import Session
from test_figure_styles import figure_course, figure_style, round_spec

from app.config import get_settings
from app.domain.enums import Difficulty, QuestionStatus, QuestionType
from app.errors import DomainRuleError, NotFoundError
from app.figures.storage import read_svg
from app.generation import GenerationService
from app.generation.computed import (
    MAX_PROGRAM_ATTEMPTS,
    ComputedProgramDraft,
    generate_computed_question,
    regenerate_copy,
)
from app.persistence.database import _alembic_config
from app.persistence.models import (
    QuestionRow,
    QuestionSubtopicRow,
    QuestionVariantRow,
    StudentAttemptRow,
)
from app.persistence.repositories import QuestionSetRepository
from app.styles import QuestionStyle
from app.web.routes.api.students import STUDENT_HEADER

#: A program whose copies differ by seed: the figure shows ``10 + seed`` and so does the key.
GOOD = """\
import json


def generate(seed):
    count = 10 + seed
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="20">'
        '<text x="2" y="14">' + str(count) + ' marks</text></svg>'
    )
    print(json.dumps({
        "prompt": "How many marks does the figure count?",
        "figure": {"svg": svg, "alt": "A label with a count of marks.", "caption": ""},
        "value": count,
        "unit": "",
        "calculation": "10 + " + str(seed),
        "explanation": "Read the count off the figure.",
    }))
"""
CRASHES = "def generate(seed):\n    raise ValueError('no data for this seed')\n"
NOT_JSON = "def generate(seed):\n    print('the answer is', seed)\n"
SLOW = "def generate(seed):\n    while True:\n        seed += 1\n"
#: Prints a copy whose answer field fails the type's draft model (``value`` is not a number).
BAD_FIELDS = GOOD.replace('"value": count', '"value": "many"')
FORBIDDEN = "import os\n\n" + GOOD


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> list[QuestionStyle]:
    import app.styles.library

    styles: list[QuestionStyle] = []
    monkeypatch.setattr(app.styles.library, "get_library", lambda subject: list(styles))
    return styles


@pytest.fixture
def env(session: Session, library: list[QuestionStyle]) -> SimpleNamespace:
    env = figure_course(
        session, subject="custom", name="Course", question_types=["numeric_response"]
    )
    env.style = figure_style(
        f"c{env.course.id}.count_marks",
        "computed",
        subject=env.profile.storage_key,
        question_type=QuestionType.NUMERIC_RESPONSE,
    )
    library.append(env.style)
    return env


def _program(env: SimpleNamespace, source: str) -> ComputedProgramDraft:
    return ComputedProgramDraft(
        topic_id=env.topic.id, subtopic_ids=[env.subtopic.id], program=source
    )


def _client(env: SimpleNamespace, *sources: str) -> SequencedDraftClient:
    return SequencedDraftClient(
        drafts=[_program(env, source) for source in sources], difficulty=Difficulty.MEDIUM
    )


def _generate(session: Session, env: SimpleNamespace, client: MetricJudgeClient):
    return generate_computed_question(
        session,
        round_spec(session, env, env.style),
        version=env.version,
        system="system",
        prompt="prompt",
        client=client,
        sources=[{"chunk_id": env.chunk_id, "citation": "notes"}],
    )


def _stored_counts(session: Session) -> tuple[int, int]:
    return (
        session.scalar(select(func.count()).select_from(QuestionRow)),
        session.scalar(select(func.count()).select_from(QuestionVariantRow)),
    )


# --- a good program ---------------------------------------------------------------------------


def test_a_program_makes_k_checked_copies_and_keeps_the_program_apart(
    session: Session, env: SimpleNamespace
) -> None:
    result = _generate(session, env, _client(env, GOOD))

    row = result.row
    assert result.problems == []
    assert row is not None
    assert [(v.ordinal, v.seed, v.content["value"]) for v in result.variants] == [
        (0, 1, 11),
        (1, 2, 12),
        (2, 3, 13),
    ]
    assert row.figure_program == GOOD
    assert "program" not in row.content
    assert (
        row.content["value"] == 11 and row.content["figure"] == result.variants[0].content["figure"]
    )
    assert row.validation_report.passed
    for variant in result.variants:
        assert variant.course_id == env.course.id
        assert variant.content["figure"]["kind"] == "computed"
        svg = read_svg(variant.content["figure"]["file"]).decode()
        assert f"{int(variant.content['value'])} marks" in svg


def test_a_round_with_a_computed_style_judges_copy_zero_and_stores_the_copies(
    session: Session, env: SimpleNamespace
) -> None:
    client = _client(env, GOOD)

    row = GenerationService(session, client=client).generate_round_question(
        round_spec(session, env, env.style), version=env.version, round_id=None
    )

    assert row is not None
    assert row.style_id == env.style.id and row.target_subtopic_id == env.subtopic.id
    assert row.pedagogical_eval["metrics"]
    assert row.personalization_context["type_instruction"]["source"] == "shipped"
    (call,) = client.generation_calls
    assert call["model"] is ComputedProgramDraft
    assert "--- computed figure ---" in call["prompt"] and "--- target ---" in call["prompt"]
    assert "Every question in this style shows the student a computed figure." in call["prompt"]
    assert _stored_counts(session) == (1, 3)


# --- a bad program is repaired or rejected, never stored --------------------------------------


def test_a_crashing_program_is_repaired_with_its_error(
    session: Session, env: SimpleNamespace
) -> None:
    client = _client(env, CRASHES, GOOD)

    result = _generate(session, env, client)

    assert result.row is not None and len(result.variants) == 3
    first, second = result.attempts
    assert [check.name for check in first.failed_checks] == ["computed_program"]
    assert "no data for this seed" in (first.failed_checks[0].evidence or "")
    assert second.usable
    repair = client.generation_calls[1]["prompt"]
    assert "--- correction ---" in repair and "crashed" in repair


@pytest.mark.parametrize(
    ("source", "problem"),
    [
        (CRASHES, "crashed"),
        (NOT_JSON, "not valid JSON"),
        (BAD_FIELDS, "field 'value'"),
        (FORBIDDEN, "imports 'os'"),
    ],
)
def test_a_program_still_failing_after_the_repair_is_rejected(
    session: Session, env: SimpleNamespace, source: str, problem: str
) -> None:
    result = _generate(session, env, _client(env, source))

    assert result.row is None and result.variants == []
    assert len(result.attempts) == MAX_PROGRAM_ATTEMPTS
    assert any(problem in line for line in result.problems), result.problems
    session.flush()
    assert _stored_counts(session) == (0, 0)


def test_a_slow_program_is_stopped_and_rejected(
    session: Session, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COMPUTED_FIGURE_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()

    result = _generate(session, env, _client(env, SLOW))

    assert result.row is None
    assert any("did not finish within 1 s" in line for line in result.problems)
    assert _stored_counts(session) == (0, 0)


def test_a_rejected_round_question_stores_nothing(session: Session, env: SimpleNamespace) -> None:
    row = GenerationService(session, client=_client(env, NOT_JSON)).generate_round_question(
        round_spec(session, env, env.style), version=env.version, round_id=None
    )

    assert row is None
    assert _stored_counts(session) == (0, 0)


# --- serving and scoring ----------------------------------------------------------------------


def _approved_set(session: Session, env: SimpleNamespace) -> tuple[int, QuestionRow]:
    result = _generate(session, env, _client(env, GOOD))
    row = result.row
    assert row is not None
    row.status = QuestionStatus.APPROVED
    if not session.scalar(
        select(QuestionSubtopicRow).where(QuestionSubtopicRow.question_id == row.id)
    ):
        session.add(QuestionSubtopicRow(question_id=row.id, subtopic_id=env.subtopic.id))
    frozen = QuestionSetRepository(session).create(
        label="Week 1", question_ids=[row.id], curriculum_version_id=env.version.id
    )
    session.commit()
    return frozen.id, row


def _serve(client: TestClient, set_id: int, name: str) -> dict:
    enrolled = client.post(
        "/api/students", json={"display_name": name, "email": f"{name.lower()}@example.edu"}
    ).json()
    client.headers[STUDENT_HEADER] = enrolled["resume_token"]
    run = client.post(
        "/api/training-sessions", json={"student_id": enrolled["id"], "set_version_id": set_id}
    )
    assert run.status_code == 201, run.text
    served = client.get(f"/api/training-sessions/{run.json()['id']}/next")
    assert served.status_code == 200, served.text
    return served.json()


def test_two_attempts_get_different_copies_each_scored_against_its_own_key(
    client: TestClient, session: Session, env: SimpleNamespace
) -> None:
    set_id, row = _approved_set(session, env)
    variants = {v.content["figure"]["file"]: v for v in session.scalars(select(QuestionVariantRow))}

    ada = _serve(client, set_id, "Ada")
    ada_token = client.headers[STUDENT_HEADER]
    bob = _serve(client, set_id, "Bob")
    bob_token = client.headers[STUDENT_HEADER]
    ada_copy = variants[ada["figure"]["file"]]
    bob_copy = variants[bob["figure"]["file"]]
    assert ada_copy.id != bob_copy.id
    assert ada["question_id"] == bob["question_id"] == row.id

    client.headers[STUDENT_HEADER] = ada_token
    right = client.post(
        f"/api/attempts/{ada['attempt_id']}/answer",
        json={"answer": str(ada_copy.content["value"])},
    )
    client.headers[STUDENT_HEADER] = bob_token
    # Bob answers with Ada's key: wrong for his copy.
    wrong = client.post(
        f"/api/attempts/{bob['attempt_id']}/answer",
        json={"answer": str(ada_copy.content["value"])},
    )
    assert right.json()["score"] == 100
    assert wrong.json()["score"] == 0

    with Session(session.get_bind()) as fresh:
        attempts = {a.id: a.variant_id for a in fresh.scalars(select(StudentAttemptRow))}
    assert attempts == {ada["attempt_id"]: ada_copy.id, bob["attempt_id"]: bob_copy.id}


def test_a_student_never_receives_the_program_or_another_copys_key(
    client: TestClient, session: Session, env: SimpleNamespace
) -> None:
    set_id, row = _approved_set(session, env)
    copies = list(session.scalars(select(QuestionVariantRow).order_by(QuestionVariantRow.ordinal)))

    served = _serve(client, set_id, "Ada")
    own = next(c for c in copies if c.content["figure"]["file"] == served["figure"]["file"])
    others = [c for c in copies if c.id != own.id]
    text = json.dumps(served)
    assert "generate(seed)" not in text and "figure_program" not in text
    assert "value" not in served and str(own.content["value"]) not in text

    client.post(f"/api/attempts/{served['attempt_id']}/answer", json={"answer": "1"})
    review = client.get(f"/api/attempts/{served['attempt_id']}/review").json()
    reviewed = json.dumps(review)
    assert review["figure_copies"] == [] and review["figure_program"] is None
    assert "def generate" not in reviewed
    assert review["content"]["value"] == own.content["value"]
    assert review["reference_solution"] == own.reference_solution
    for other in others:
        assert other.content["figure"]["file"] not in reviewed

    client.headers.pop(STUDENT_HEADER)
    professor = client.get(f"/api/questions/{row.id}").json()
    assert professor["figure_program"] == GOOD
    assert [c["content"]["value"] for c in professor["figure_copies"]] == [11, 12, 13]


# --- regenerating one copy (fig6 calls this) --------------------------------------------------


def test_one_copy_is_regenerated_from_the_program_for_a_new_seed(
    session: Session, env: SimpleNamespace
) -> None:
    row = _generate(session, env, _client(env, GOOD)).row
    assert row is not None

    replaced = regenerate_copy(session, row.id, 1)
    first = regenerate_copy(session, row.id, 0)

    assert (replaced.seed, replaced.content["value"]) == (4, 14)
    assert (first.seed, first.content["value"]) == (5, 15)
    assert row.content["value"] == 15 and row.content["figure"] == first.content["figure"]
    assert row.content["sources"] and row.prompt == first.prompt
    with pytest.raises(NotFoundError, match="Copy not found"):
        regenerate_copy(session, row.id, 7)


def test_a_copy_a_student_was_served_is_kept(
    client: TestClient, session: Session, env: SimpleNamespace
) -> None:
    set_id, row = _approved_set(session, env)
    served = _serve(client, set_id, "Ada")
    with Session(session.get_bind()) as fresh:
        attempt = fresh.get(StudentAttemptRow, served["attempt_id"])
        ordinal = fresh.get(QuestionVariantRow, attempt.variant_id).ordinal

    with pytest.raises(DomainRuleError, match="already answered"):
        regenerate_copy(session, row.id, ordinal)

    refused = client.post(f"/api/questions/{row.id}/copies/{ordinal}/regenerate")
    assert refused.status_code == 422, refused.text
    assert "already answered" in refused.text


def test_the_professor_regenerates_one_copy_through_the_api(
    client: TestClient, session: Session, env: SimpleNamespace
) -> None:
    row = _generate(session, env, _client(env, GOOD)).row
    assert row is not None
    session.commit()

    response = client.post(f"/api/questions/{row.id}/copies/1/regenerate")

    assert response.status_code == 200, response.text
    copies = response.json()["figure_copies"]
    assert [(c["seed"], c["content"]["value"]) for c in copies] == [(1, 11), (4, 14), (3, 13)]
    assert read_svg(copies[1]["content"]["figure"]["file"])
    missing = client.post(f"/api/questions/{row.id}/copies/9/regenerate")
    assert missing.status_code == 404


def test_a_computed_figure_edit_changes_only_its_words(
    session: Session, env: SimpleNamespace
) -> None:
    from app.domain.enums import ReviewDecision
    from app.feedback import submit_review

    row = _generate(session, env, _client(env, GOOD)).row
    assert row is not None
    figure = dict(row.content["figure"])

    def edit(new: dict) -> object:
        return submit_review(
            session,
            question_id=row.id,
            decision=ReviewDecision.EDIT,
            prompt=row.prompt,
            reference_solution=row.reference_solution,
            tests=row.tests or "",
            figure=new,
        )

    with pytest.raises(DomainRuleError, match="edit only its alt text"):
        edit({**figure, "file": "1/" + "b" * 64 + ".svg"})
    review = edit({**figure, "alt": "Eleven marks in a row."})

    first = session.scalar(select(QuestionVariantRow).where(QuestionVariantRow.ordinal == 0))
    assert review.changed_fields == ["figure"]
    assert (
        row.content["figure"]["alt"] == first.content["figure"]["alt"] == "Eleven marks in a row."
    )
    assert row.original_figure == figure


# --- the migration ----------------------------------------------------------------------------


def test_the_variants_migration_downgrades_and_upgrades_cleanly(engine: Engine) -> None:
    with engine.begin() as connection:
        config = _alembic_config(connection)
        command.downgrade(config, "0033_agent_threads")
        assert "question_variants" not in inspect(connection).get_table_names()
        assert "figure_program" not in {
            c["name"] for c in inspect(connection).get_columns("questions")
        }
        assert "variant_id" not in {
            c["name"] for c in inspect(connection).get_columns("student_attempts")
        }
        command.upgrade(config, "head")
        assert "question_variants" in inspect(connection).get_table_names()
        assert "figure_program" in {c["name"] for c in inspect(connection).get_columns("questions")}
        foreign = inspect(connection).get_foreign_keys("student_attempts")
        assert any(key["referred_table"] == "question_variants" for key in foreign)
