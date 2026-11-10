"""fig3: dedup, the blind solver and the judges read a question's figure as text (ADR-080)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from llm_fakes import MetricJudgeClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_dedup import TokenEmbedder
from test_evaluation_service import _seed_question

from app.domain.enums import JudgeMetricId, QuestionStatus, QuestionType, RejectionReason
from app.domain.questions import Question
from app.evaluation.prompts import (
    FIGURE_ISSUE_GUIDE,
    RUBRIC_VERSION,
    build_user_prompt,
    system_prompt_for,
)
from app.evaluation.schema import IssuesVerdict
from app.evaluation.service import PedagogicalJudge, build_judge_context
from app.evaluation.severity import issues_are_clear
from app.figures.text import figure_as_text
from app.generation.solve import BlindSolver, SolveVerdict, student_view
from app.persistence.models import QuestionRow, QuestionSimilarityRow
from app.retrieval.duplicates import DuplicateChecker, embed_text, text_hash
from app.subjects import PYTHON_PROFILE
from app.web.routes.api.dedup import flag_possible_duplicates


def _chart(value: float, *, label: str = "Count") -> dict[str, Any]:
    return {
        "kind": "chart",
        "alt": "A bar chart of counts per group.",
        "caption": "Counts per group",
        "chart": {
            "type": "bar",
            "x_title": "Group",
            "y_title": label,
            "data": {
                "labels": ["A", "B"],
                "datasets": [{"label": label, "data": [value, 7]}],
            },
        },
    }


DIAGRAM = {
    "kind": "diagram",
    "alt": "Three steps in a row.",
    "caption": "",
    "source": "flowchart LR\n  P-->Q-->R",
}
COMPUTED = {
    "kind": "computed",
    "alt": "A plotted curve.",
    "caption": "Curve",
    "file": "1/" + "a" * 64 + ".svg",
}

STEM = "Which group has the larger count in the chart?"


# --- figure_as_text --------------------------------------------------------------------------


def test_figure_as_text_is_deterministic_and_carries_every_value() -> None:
    first = figure_as_text(_chart(42))
    reordered = json.loads(json.dumps(_chart(42), sort_keys=True))
    assert figure_as_text(reordered) == first == figure_as_text(_chart(42.0))
    assert first.splitlines() == [
        "Figure (chart): Counts per group",
        "Alt text: A bar chart of counts per group.",
        "Chart type: bar",
        "X axis: Group",
        "Y axis: Count",
        "Labels: A, B",
        'Series "Count": A = 42, B = 7',
    ]
    assert figure_as_text(_chart(42)) != figure_as_text(_chart(45))


def test_figure_as_text_for_each_kind() -> None:
    assert figure_as_text(None) == ""
    assert figure_as_text(DIAGRAM).splitlines() == [
        "Figure (diagram)",
        "Alt text: Three steps in a row.",
        "Mermaid source:",
        "flowchart LR",
        "  P-->Q-->R",
    ]
    # A computed SVG is a file: only its words reach a text reader.
    assert figure_as_text(COMPUTED) == "Figure (computed): Curve\nAlt text: A plotted curve."
    scatter = {
        "kind": "chart",
        "alt": "Points.",
        "chart": {
            "type": "scatter",
            "data": {"datasets": [{"label": "p", "data": [{"x": 1, "y": 2.5}]}]},
        },
    }
    assert figure_as_text(scatter).endswith('Series "p": (1, 2.5)')
    assert figure_as_text({"kind": "chart"}).startswith("Figure (unreadable): ")


# --- dedup -----------------------------------------------------------------------------------


def _row(session: Session, figure: dict[str, Any] | None) -> QuestionRow:
    content: dict[str, Any] = {"options": ["A", "B"]}
    if figure is not None:
        content["figure"] = figure
    row = QuestionRow(
        prompt=STEM,
        topic_id=1,
        status=QuestionStatus.VALIDATION_PASSED,
        content=content,
        generator_name="test-gen",
        generator_version="1",
    )
    session.add(row)
    session.commit()
    return row


def test_same_wording_with_different_figures_is_not_a_duplicate(session: Session) -> None:
    one = embed_text(STEM, {"options": ["A", "B"], "figure": _chart(42)})
    two = embed_text(STEM, {"options": ["A", "B"], "figure": _chart(45)})
    assert one != two and text_hash(one) != text_hash(two)
    assert embed_text(STEM, {"options": ["A", "B"]}) == f"{STEM}\nA\nB"

    _row(session, _chart(42))
    new = _row(session, DIAGRAM)
    assert flag_possible_duplicates(session, TokenEmbedder(), [new]) == 0
    assert list(session.scalars(select(QuestionSimilarityRow))) == []


def test_same_wording_and_same_figure_is_still_an_exact_duplicate(session: Session) -> None:
    existing = _row(session, _chart(42))

    (match,) = DuplicateChecker(session, TokenEmbedder()).similar(
        topic_id=1, prompt=STEM, content={"options": ["A", "B"], "figure": _chart(42)}
    )
    assert (match.question_id, match.exact) == (existing.id, True)
    matches = DuplicateChecker(session, None).similar(
        topic_id=1, prompt=STEM, content={"options": ["A", "B"], "figure": _chart(45)}
    )
    assert matches == []


# --- blind solver ----------------------------------------------------------------------------


class _Solver:
    description = "fake/solver"

    def __init__(self, verdict: SolveVerdict) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, str]] = []

    def complete_structured(self, *, system: str, prompt: str, response_model: Any) -> Any:
        self.calls.append((system, prompt))
        return self.verdict


def _mismatch() -> Question:
    """The chart says A is 42; the key says 45."""
    return Question(
        prompt="What count does the chart show for group A?",
        question_type=QuestionType.MULTIPLE_CHOICE,
        content={"options": ["42", "45", "7"], "correct_option_index": 1, "figure": _chart(42)},
    )


def test_a_chart_key_mismatch_reaches_the_solver_and_is_flagged() -> None:
    solver = _Solver(SolveVerdict(answer="A", correct_options=["A"], exactly_one_correct=True))

    (finding,) = BlindSolver(clients={"x/solver": solver})(_mismatch())  # type: ignore[dict-item]

    system, prompt = solver.calls[0]
    assert 'Series "Count": A = 42, B = 7' in prompt
    assert "Alt text: A bar chart of counts per group." in prompt
    assert "B. 45" in prompt and "correct_option_index" not in prompt
    assert "figure" in system
    assert finding.describe("B") == "solver answered A (key is B)"


def test_a_true_false_question_shows_its_figure_too() -> None:
    question = Question(
        prompt="The flow has three steps.",
        question_type=QuestionType.TRUE_FALSE,
        content={"correct_answer": True, "figure": DIAGRAM},
    )
    text, key = student_view(question)  # type: ignore[misc]
    assert key == "A"
    assert "flowchart LR\n  P-->Q-->R" in text
    assert text.endswith("Options:\nA. True\nB. False")


# --- judges ----------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def four_metric_panel(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("JUDGE_METRICS_ENABLED", "issues,subtopic,difficulty,generatability")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _RecordingJudge(MetricJudgeClient):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.systems: dict[str, str] = {}

    def complete_structured(self, *, system: str, prompt: str, response_model: Any, **kw: Any):
        self.systems[response_model.__name__] = system
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kw
        )


def _with_figure(question: Question, figure: dict[str, Any]) -> Question:
    return question.model_copy(update={"content": {**(question.content or {}), "figure": figure}})


def _judge(question: Question) -> _RecordingJudge:
    return _RecordingJudge(
        topic_id=question.topic_id or 0,
        subtopic_ids=list(question.subtopic_ids),
        difficulty=question.difficulty,
    )


def test_the_judge_payload_carries_the_figure_as_text(session: Session, settings: Any) -> None:
    question = _with_figure(_seed_question(session, settings), _chart(42))

    context = build_judge_context(session, question)
    for metric in (JudgeMetricId.ISSUES, JudgeMetricId.SUBTOPIC, JudgeMetricId.DIFFICULTY):
        payload = json.loads(build_user_prompt(metric, context))
        assert payload["question"]["figure"] == figure_as_text(_chart(42))
        assert "figure" not in payload["question"]["content"]
    generatability = json.loads(build_user_prompt(JudgeMetricId.GENERATABILITY, context))
    assert "question" not in generatability


def test_a_question_without_a_figure_keeps_its_payload_panel_and_rubric(
    session: Session, settings: Any
) -> None:
    question = _seed_question(session, settings)
    payload = json.loads(
        build_user_prompt(JudgeMetricId.ISSUES, build_judge_context(session, question))
    )
    assert "figure" not in payload["question"]
    assert payload["question"]["content"] == question.content

    client = _judge(question)
    result = PedagogicalJudge(session, client=client).evaluate(question)

    assert result.rubric_version == RUBRIC_VERSION
    assert FIGURE_ISSUE_GUIDE not in client.systems["IssuesVerdict"]
    assert RejectionReason.FIGURE_MISMATCH.value not in system_prompt_for(
        JudgeMetricId.ISSUES, PYTHON_PROFILE
    )


def test_a_figure_question_gets_the_figure_code_and_its_own_panel_name(
    session: Session, settings: Any
) -> None:
    question = _with_figure(_seed_question(session, settings), _chart(42))
    client = _judge(question)
    client.issue_codes = [RejectionReason.FIGURE_MISMATCH]

    result = PedagogicalJudge(session, client=client).evaluate(question)

    assert result.rubric_version == f"{RUBRIC_VERSION}+figure"
    assert client.systems["IssuesVerdict"].count("figure_mismatch") == 1
    assert "figure_mismatch" not in client.systems["DifficultyVerdict"]
    issues = result.metric(JudgeMetricId.ISSUES)
    assert issues is not None and issues.passed is False
    assert issues.issue_codes == [RejectionReason.FIGURE_MISMATCH]
    assert issues_are_clear([RejectionReason.FIGURE_MISMATCH])
    assert IssuesVerdict(issue_codes=["figure_mismatch"], rationale="r").issue_codes == [
        RejectionReason.FIGURE_MISMATCH
    ]
