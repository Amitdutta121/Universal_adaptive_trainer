"""Editing a judge's prompt, and what that does to its identity (ADR-038).

A repaired judge has to be distinguishable from the one it replaced, or the
held-back check questions of ADR-035 have nothing to score. These check that the
edited text actually reaches the judge, that the panel is re-named whenever the
prompts change, and that stored verdicts are left alone.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, JudgeMetricId, QuestionStatus, QuestionType
from app.domain.questions import Question
from app.evaluation.judge_prompts import (
    effective_rubric_version,
    is_edited,
    resolve_system_prompts,
)
from app.evaluation.prompts import RUBRIC_VERSION, SYSTEM_PROMPT_FOR, JudgeContext
from app.persistence.models import QuestionRow
from app.persistence.repositories import JudgePromptRepository, QuestionRepository

REPLACEMENT = "You judge difficulty. Treat anything with a loop as hard."


def _save(session: Session, metric: JudgeMetricId, text: str) -> None:
    JudgePromptRepository(session).save(metric, system_prompt=text, note=None)
    session.commit()


def _question(session: Session) -> Question:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Write a loop.",
            question_type=QuestionType.CODING,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
        )
    )
    session.commit()
    return Question.model_validate(row)


# ---------------------------------------------------------------- what runs


def test_an_untouched_installation_runs_the_shipped_prompts(session: Session) -> None:
    assert resolve_system_prompts(session) == SYSTEM_PROMPT_FOR
    assert effective_rubric_version(session) == RUBRIC_VERSION
    assert not is_edited(session, JudgeMetricId.DIFFICULTY)


def test_an_edited_prompt_is_what_the_judge_runs(session: Session) -> None:
    _save(session, JudgeMetricId.DIFFICULTY, REPLACEMENT)

    prompts = resolve_system_prompts(session)

    assert prompts[JudgeMetricId.DIFFICULTY] == REPLACEMENT
    assert prompts[JudgeMetricId.ISSUES] == SYSTEM_PROMPT_FOR[JudgeMetricId.ISSUES]
    assert is_edited(session, JudgeMetricId.DIFFICULTY)


def test_the_judge_sends_the_edited_prompt(session: Session, monkeypatch) -> None:
    """Not just stored: the text has to reach the provider call."""
    from app.evaluation.service import PedagogicalJudge

    _save(session, JudgeMetricId.DIFFICULTY, REPLACEMENT)
    seen: list[str] = []

    class RecordingClient:
        description = "fake/judge"

        def complete_structured(self, *, system: str, prompt: str, response_model):
            seen.append(system)
            raise RuntimeError("stop after recording")

    context = JudgeContext(
        question_artifact={"prompt": "Write a loop."},
        source_sections=[],
        taxonomy=[],
        claimed_taxonomy={},
        requested_difficulty="easy",
        requested_question_type="coding",
    )
    judge = PedagogicalJudge(session, client=RecordingClient())
    with pytest.raises(RuntimeError):
        judge._run_metric(
            JudgeMetricId.DIFFICULTY,
            context,
            _question(session),
        )

    assert seen == [REPLACEMENT]


# ------------------------------------------------------------ panel identity


def test_editing_re_names_the_panel(session: Session) -> None:
    before = effective_rubric_version(session)

    _save(session, JudgeMetricId.DIFFICULTY, REPLACEMENT)

    after = effective_rubric_version(session)
    assert after != before
    assert after.startswith(RUBRIC_VERSION + "+")


def test_two_different_prompt_sets_never_share_a_name(session: Session) -> None:
    _save(session, JudgeMetricId.DIFFICULTY, REPLACEMENT)
    one = effective_rubric_version(session)

    _save(session, JudgeMetricId.ISSUES, "You judge issues. Be strict.")
    two = effective_rubric_version(session)

    assert one != two


def test_reverting_restores_the_shipped_name(session: Session) -> None:
    """Same prompts, same name: the version identifies content, not history."""
    _save(session, JudgeMetricId.DIFFICULTY, REPLACEMENT)
    JudgePromptRepository(session).delete(JudgeMetricId.DIFFICULTY)
    session.commit()

    assert effective_rubric_version(session) == RUBRIC_VERSION


def test_re_editing_one_judge_counts_the_edits(session: Session) -> None:
    _save(session, JudgeMetricId.DIFFICULTY, REPLACEMENT)
    _save(session, JudgeMetricId.DIFFICULTY, REPLACEMENT + " Be brief.")

    row = JudgePromptRepository(session).get(JudgeMetricId.DIFFICULTY)
    assert row is not None
    assert row.revision == 2


def test_a_new_evaluation_carries_the_edited_version(session: Session) -> None:
    from app.evaluation.service import PedagogicalJudge

    _save(session, JudgeMetricId.DIFFICULTY, REPLACEMENT)

    class BrokenClient:
        description = "fake/judge"

        def complete_structured(self, *, system: str, prompt: str, response_model):
            raise RuntimeError("no provider")

    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="Write a loop.",
            question_type=QuestionType.CODING,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
        )
    )
    session.commit()

    from app.domain.questions import Question

    evaluation = PedagogicalJudge(session, client=BrokenClient()).evaluate(
        Question.model_validate(question)
    )

    assert evaluation.rubric_version == effective_rubric_version(session)
    assert evaluation.rubric_version != RUBRIC_VERSION


# --------------------------------------------------------------------- the API


def test_the_api_lists_every_judge_with_its_shipped_text(client: TestClient) -> None:
    response = client.get("/api/judge-prompts")

    assert response.status_code == 200
    body = response.json()
    assert [row["metric"] for row in body["prompts"]] == [m.value for m in JudgeMetricId]
    assert body["rubric_version"] == RUBRIC_VERSION
    assert all(row["edited"] is False for row in body["prompts"])
    assert all(row["system_prompt"] == row["shipped_prompt"] for row in body["prompts"])


def test_the_api_saves_and_reports_the_new_version(client: TestClient) -> None:
    response = client.put(
        "/api/judge-prompts/difficulty",
        json={"system_prompt": REPLACEMENT, "note": "It called everything medium."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["prompt"]["system_prompt"] == REPLACEMENT
    assert body["prompt"]["edited"] is True
    assert body["prompt"]["note"] == "It called everything medium."
    assert body["rubric_version_changed"] is True
    assert body["rubric_version"] != RUBRIC_VERSION


def test_the_api_refuses_an_empty_prompt(client: TestClient) -> None:
    response = client.put("/api/judge-prompts/difficulty", json={"system_prompt": "   "})

    assert response.status_code == 422


def test_the_api_reverts(client: TestClient) -> None:
    client.put("/api/judge-prompts/difficulty", json={"system_prompt": REPLACEMENT})

    response = client.delete("/api/judge-prompts/difficulty")

    assert response.status_code == 200
    assert response.json()["prompt"]["edited"] is False
    assert response.json()["rubric_version"] == RUBRIC_VERSION


def test_reverting_a_shipped_judge_is_not_found(client: TestClient) -> None:
    response = client.delete("/api/judge-prompts/difficulty")

    assert response.status_code == 404


def test_saving_does_not_rewrite_stored_verdicts(client: TestClient, session: Session) -> None:
    """The pairs a repair is scored against must survive the repair."""
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="Write a loop.",
            question_type=QuestionType.CODING,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval={"status": "completed", "rubric_version": RUBRIC_VERSION},
        )
    )
    session.commit()

    client.put("/api/judge-prompts/difficulty", json={"system_prompt": REPLACEMENT})

    session.expire_all()
    stored = QuestionRepository(session).get(question.id)
    assert stored.pedagogical_eval["rubric_version"] == RUBRIC_VERSION


# -------------------------------------------------------------------- the page


def test_the_page_shows_the_four_judges(client: TestClient) -> None:
    response = client.get("/judges")

    assert response.status_code == 200
    for metric in JudgeMetricId:
        assert metric.value.replace("_", " ") in response.text.lower()


def test_the_page_saves_and_reports_the_version(client: TestClient) -> None:
    response = client.post(
        "/judges/difficulty",
        data={"system_prompt": REPLACEMENT, "note": "too lenient"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "saved" in response.text.lower()
    # A prompt the professor typed is labelled hand-written, not learned: it is
    # the one state the automatic repair leaves alone (ADR-039).
    assert "hand-written" in response.text.lower()


def test_the_page_reverts(client: TestClient) -> None:
    client.post("/judges/difficulty", data={"system_prompt": REPLACEMENT}, follow_redirects=True)

    response = client.post("/judges/difficulty", data={"revert": "1"}, follow_redirects=True)

    assert response.status_code == 200
    assert "reverted" in response.text.lower()


def test_the_page_says_a_saved_prompt_does_not_re_judge_the_bank(client: TestClient) -> None:
    """The page must not imply the repair has been measured when it has not."""
    response = client.get("/judges")

    assert "not rewritten" in response.text.lower()
    assert "re-judge" in response.text.lower()


def test_the_navigation_offers_the_judges_page(client: TestClient) -> None:
    response = client.get("/")

    assert "/judges" in response.text
