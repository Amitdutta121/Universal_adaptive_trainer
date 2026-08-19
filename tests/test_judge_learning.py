"""Learning a judge's prompt from its own mistakes (ADR-039).

The mirror of ``test_type_instructions.py``. Same three questions asked of the
judge side: it is only learned from real disagreements, the learned text reaches
the judge, and rules accumulate rather than being rewritten away. Plus the guard
personalization does not need -- the held-out third must never be read.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from llm_fakes import metric_results
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.enums import (
    Difficulty,
    JudgeGate,
    JudgeMetricId,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.evaluation import PedagogicalEvalStatus, PedagogicalEvaluation
from app.evaluation.judge_learning import (
    LearnedJudgeRule,
    LearnedJudgeRules,
    disagreements_for,
    refresh_judge_prompt,
    render_judge_prompt,
)
from app.evaluation.judge_prompts import effective_rubric_version, resolve_system_prompts
from app.evaluation.prompts import RUBRIC_VERSION, SYSTEM_PROMPT_FOR
from app.feedback import route_review_outcome, submit_review
from app.persistence.models import QuestionRow
from app.persistence.repositories import JudgePromptRepository, QuestionRepository

DIFFICULTY = JudgeMetricId.DIFFICULTY


class Rewriter:
    """Returns a fixed rule set, and records what it was shown."""

    def __init__(self, rules: list[dict[str, Any]] | None = None) -> None:
        self.rules = rules if rules is not None else [{"rule": "A loop alone is not hard."}]
        self.prompts: list[str] = []
        self.calls = 0

    @property
    def description(self) -> str:
        return "fake/rewriter"

    def complete_structured(self, *, system: str, prompt: str, response_model: type[BaseModel]):
        self.calls += 1
        self.prompts.append(prompt)
        return LearnedJudgeRules(rules=[LearnedJudgeRule(**rule) for rule in self.rules])


@pytest.fixture
def rewriter(monkeypatch: pytest.MonkeyPatch) -> Rewriter:
    fake = Rewriter()
    monkeypatch.setattr("app.evaluation.judge_learning.get_structured_client", lambda: fake)
    return fake


def _evaluation(gate: JudgeGate, *, failing: set[JudgeMetricId], rationale: str) -> dict[str, Any]:
    metrics = metric_results(failing=failing)
    for result in metrics:
        result.rationale = rationale
    return PedagogicalEvaluation(
        status=PedagogicalEvalStatus.COMPLETED,
        gate=gate,
        metrics=metrics,
        judge_model="fake/judge",
    ).model_dump(mode="json")


def _disagreement(
    session: Session,
    *,
    gate: JudgeGate = JudgeGate.APPROVED,
    failing: set[JudgeMetricId] | None = None,
    decision: ReviewDecision = ReviewDecision.REJECT,
    reasons: list[RejectionReason] | None = None,
    rationale: str = "One taught step, so easy is right.",
) -> QuestionRow:
    """A question the difficulty judge got wrong, routed into the dataset."""
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(gate, failing=failing or set(), rationale=rationale),
        )
    )
    session.commit()
    review = submit_review(
        session,
        question_id=question.id,
        decision=decision,
        reasons=reasons if reasons is not None else [RejectionReason.TOO_EASY],
    )
    session.commit()
    route_review_outcome(session, review)
    session.commit()
    return question


# ------------------------------------------------------------------ the evidence


def test_a_judge_nobody_contradicted_learns_nothing(session: Session, rewriter: Rewriter) -> None:
    assert refresh_judge_prompt(session, DIFFICULTY) is None
    assert rewriter.calls == 0
    assert resolve_system_prompts(session) == SYSTEM_PROMPT_FOR


def test_only_the_cases_naming_this_judge_are_used(session: Session) -> None:
    _disagreement(session, reasons=[RejectionReason.TOO_EASY])
    _disagreement(session, reasons=[RejectionReason.WRONG_TOPIC_SUBTOPIC])

    difficulty = disagreements_for(session, DIFFICULTY)
    subtopic = disagreements_for(session, JudgeMetricId.SUBTOPIC)

    assert len(difficulty) == 1
    assert len(subtopic) == 1
    assert difficulty[0].question_id != subtopic[0].question_id


def test_the_held_out_third_is_never_read(session: Session) -> None:
    """A judge tuned on its own check set reports fitting as improvement."""
    for _ in range(6):
        _disagreement(session)

    usable = disagreements_for(session, DIFFICULTY)

    assert usable, "some disagreements must remain to learn from"
    assert all(not row.held_out for row in usable)
    assert all(row.question_id % 3 != 0 for row in usable)


def test_the_rewriter_is_shown_the_case_and_what_the_judge_said(
    session: Session, rewriter: Rewriter
) -> None:
    _disagreement(session, rationale="One taught step, so easy is right.")

    refresh_judge_prompt(session, DIFFICULTY)

    prompt = rewriter.prompts[0]
    assert "One taught step, so easy is right." in prompt
    assert "What does this loop print?" in prompt
    assert "Too easy" in prompt
    assert "passed" in prompt


def test_the_rewriter_sees_the_question_the_judge_judged_not_the_edit(
    session: Session, rewriter: Rewriter
) -> None:
    """An edit overwrites ``prompt``; quoting it would show a fixed question."""
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(
                JudgeGate.APPROVED, failing=set(), rationale="Easy is right."
            ),
        )
    )
    session.commit()
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.EDIT,
        reasons=[RejectionReason.TOO_EASY],
        prompt="What does this nested loop print, and in what order?",
        reference_solution="",
        tests="",
    )
    session.commit()
    route_review_outcome(session, review)
    session.commit()

    refresh_judge_prompt(session, DIFFICULTY)

    prompt = rewriter.prompts[0]
    assert '"question":"What does this loop print?"' in prompt
    assert "nested loop" in prompt
    assert "professor_corrected" in prompt


def test_only_the_fields_the_professor_changed_are_quoted(
    session: Session, rewriter: Rewriter
) -> None:
    """A tests-only fix must not look like a prompt rewritten into itself."""
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            original_prompt="What does this loop print?",
            reference_solution="print(1)",
            original_reference_solution="print(1)",
            tests="assert True",
            original_tests="assert True",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(JudgeGate.APPROVED, failing=set(), rationale="Easy."),
        )
    )
    session.commit()
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.EDIT,
        reasons=[RejectionReason.TOO_EASY],
        prompt="What does this loop print?",
        reference_solution="print(1)",
        tests="assert output == '1\\n2\\n3'",
    )
    session.commit()
    route_review_outcome(session, review)
    session.commit()

    refresh_judge_prompt(session, DIFFICULTY)

    prompt = rewriter.prompts[0]
    assert '"professor_corrected":{"tests":' in prompt
    assert "output ==" in prompt
    # The prompt did not move, so it must not be reported as a correction.
    assert '"professor_corrected":{"prompt"' not in prompt


def test_a_comment_reaches_the_rewriter(session: Session, rewriter: Rewriter) -> None:
    """A comment cannot name a judge, but it is evidence once one is named."""
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(JudgeGate.APPROVED, failing=set(), rationale="Easy."),
        )
    )
    session.commit()
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
        comment="Any student who has met a for-loop answers this instantly.",
    )
    session.commit()
    route_review_outcome(session, review)
    session.commit()

    refresh_judge_prompt(session, DIFFICULTY)

    assert "answers this instantly" in rewriter.prompts[0]


def test_a_comment_alone_names_no_judge(session: Session, rewriter: Rewriter) -> None:
    """Prose is not a structured reason, so nothing can be compared against it."""
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(JudgeGate.APPROVED, failing=set(), rationale="Easy."),
        )
    )
    session.commit()
    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.EDIT,
        comment="This is far too easy.",
        prompt="What does this nested loop print?",
        reference_solution="",
        tests="",
    )
    session.commit()

    outcome = route_review_outcome(session, review)

    assert outcome is not None
    assert outcome.attributed_metrics == []
    assert disagreements_for(session, DIFFICULTY) == []


def test_the_rewriter_is_shown_the_rules_it_already_has(
    session: Session, rewriter: Rewriter
) -> None:
    _disagreement(session)
    refresh_judge_prompt(session, DIFFICULTY)

    _disagreement(session)
    refresh_judge_prompt(session, DIFFICULTY)

    assert "A loop alone is not hard." in rewriter.prompts[1]


# ------------------------------------------------------------- what it produces


def test_the_learned_rules_are_added_onto_the_shipped_prompt(
    session: Session, rewriter: Rewriter
) -> None:
    """The shipped text is the contract; a rewrite must not be free to drop it."""
    _disagreement(session)

    row = refresh_judge_prompt(session, DIFFICULTY)

    assert row is not None
    assert row.system_prompt.startswith(SYSTEM_PROMPT_FOR[DIFFICULTY])
    assert "A loop alone is not hard." in row.system_prompt
    assert row.learned is True
    assert row.evidence_count == 1


def test_the_learned_prompt_is_what_the_judge_runs(session: Session, rewriter: Rewriter) -> None:
    _disagreement(session)

    refresh_judge_prompt(session, DIFFICULTY)

    prompts = resolve_system_prompts(session)
    assert "A loop alone is not hard." in prompts[DIFFICULTY]
    assert prompts[JudgeMetricId.ISSUES] == SYSTEM_PROMPT_FOR[JudgeMetricId.ISSUES]


def test_learning_re_names_the_panel(session: Session, rewriter: Rewriter) -> None:
    _disagreement(session)

    refresh_judge_prompt(session, DIFFICULTY)

    assert effective_rubric_version(session) != RUBRIC_VERSION


def test_render_keeps_the_shipped_text_when_nothing_is_learned() -> None:
    assert render_judge_prompt("Base text.", []) == "Base text."


# ------------------------------------------------------- firing on a submitted review


def test_a_disagreeing_review_relearns_the_named_judge(
    client: TestClient, session: Session, rewriter: Rewriter
) -> None:
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(
                JudgeGate.APPROVED, failing=set(), rationale="Easy is right."
            ),
        )
    )
    session.commit()
    # Question 1 is not held out, so this disagreement is learnable.
    assert question.id % 3 != 0

    response = client.post(
        f"/api/questions/{question.id}/review",
        json={"decision": "reject", "reasons": ["too_easy"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["outcome"]["cell"] == "missed"
    assert body["outcome"]["judges_refreshed"] == [DIFFICULTY.value]
    assert rewriter.calls == 1

    row = JudgePromptRepository(session).get(DIFFICULTY)
    assert row is not None
    assert row.learned is True


def test_an_agreeing_review_relearns_no_judge(
    client: TestClient, session: Session, rewriter: Rewriter
) -> None:
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(JudgeGate.APPROVED, failing=set(), rationale="Fine."),
        )
    )
    session.commit()

    response = client.post(f"/api/questions/{question.id}/review", json={"decision": "approve"})

    assert response.json()["outcome"]["judges_refreshed"] == []
    assert rewriter.calls == 0


def test_a_hand_written_judge_is_never_overwritten(
    client: TestClient, session: Session, rewriter: Rewriter
) -> None:
    """The professor typed it deliberately; a learned rewrite would discard it."""
    JudgePromptRepository(session).save(
        DIFFICULTY, system_prompt="My own difficulty rules.", note=None
    )
    session.commit()

    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(JudgeGate.APPROVED, failing=set(), rationale="Easy."),
        )
    )
    session.commit()

    client.post(
        f"/api/questions/{question.id}/review",
        json={"decision": "reject", "reasons": ["too_easy"]},
    )

    assert rewriter.calls == 0
    row = JudgePromptRepository(session).get(DIFFICULTY)
    assert row is not None
    assert row.system_prompt == "My own difficulty rules."


def test_a_failed_relearn_keeps_the_review(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.errors import LLMRequestError

    def boom():
        class Failing:
            description = "fake/rewriter"

            def complete_structured(self, **_kwargs):
                raise LLMRequestError("The provider is unavailable.", detail="502")

        return Failing()

    monkeypatch.setattr("app.evaluation.judge_learning.get_structured_client", boom)
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="What does this loop print?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            pedagogical_eval=_evaluation(JudgeGate.APPROVED, failing=set(), rationale="Easy."),
        )
    )
    session.commit()

    response = client.post(
        f"/api/questions/{question.id}/review",
        json={"decision": "reject", "reasons": ["too_easy"]},
    )

    assert response.status_code == 201
    outcome = response.json()["outcome"]
    assert outcome["judges_refreshed"] == []
    assert "provider" in (outcome["refresh_error"] or "").lower()


# --------------------------------------------------------------- the API and page


def test_the_api_refreshes_one_judge(
    client: TestClient, session: Session, rewriter: Rewriter
) -> None:
    _disagreement(session)

    response = client.post(f"/api/judge-prompts/{DIFFICULTY.value}/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["learned"] is True
    assert body["rule_count"] == 1
    assert body["rubric_version_changed"] is True
    assert body["prompt"]["rules"] == ["A loop alone is not hard."]


def test_the_api_reports_nothing_to_learn_from(client: TestClient, rewriter: Rewriter) -> None:
    response = client.post(f"/api/judge-prompts/{DIFFICULTY.value}/refresh")

    assert response.status_code == 200
    assert response.json()["learned"] is False
    assert response.json()["rubric_version"] == RUBRIC_VERSION


def test_the_api_counts_what_is_available_to_learn_from(
    client: TestClient, session: Session
) -> None:
    _disagreement(session)

    body = client.get("/api/judge-prompts").json()
    by_metric = {row["metric"]: row for row in body["prompts"]}

    assert by_metric[DIFFICULTY.value]["available_disagreements"] == 1
    assert by_metric[JudgeMetricId.ISSUES.value]["available_disagreements"] == 0
