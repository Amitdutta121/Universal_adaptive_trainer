"""m12 learning-curve script: flatten detection and the stored-verdict smoke path."""

from __future__ import annotations

from app.domain.enums import (
    Difficulty,
    JudgeMetricId,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.memory import SOURCE_REVIEW
from app.persistence.models import MemoryEpisodeRow, QuestionRow
from app.persistence.repositories import QuestionRepository
from app.subjects import PYTHON_PROFILE
from scripts.learning_curve import curve_from_store, flatten_point


def test_flatten_point_is_the_first_prefix_that_gains_under_one_point() -> None:
    series = [(10, 50.0), (20, 62.0), (40, 70.0), (80, 71.0), (160, 71.2)]
    assert flatten_point(series) == 80


def test_flatten_point_is_none_while_still_climbing() -> None:
    series = [(10, 40.0), (20, 55.0), (40, 70.0), (80, 82.0)]
    assert flatten_point(series) is None


def test_curve_from_store_reports_counts(session) -> None:
    for index in range(12):
        question = QuestionRepository(session).add(
            QuestionRow(
                prompt=f"Loop question {index}",
                question_type=QuestionType.MULTIPLE_CHOICE,
                difficulty=Difficulty.EASY,
                status=QuestionStatus.APPROVED,
            )
        )
        session.flush()
        session.add(
            MemoryEpisodeRow(
                question_id=question.id,
                source=SOURCE_REVIEW,
                subject=PYTHON_PROFILE.personal_key,
                question_type=QuestionType.MULTIPLE_CHOICE,
                difficulty=Difficulty.EASY,
                text=question.prompt,
                decision=ReviewDecision.APPROVE if index % 2 == 0 else ReviewDecision.REJECT,
                reasons=[] if index % 2 == 0 else [RejectionReason.TOO_EASY],
                judge_verdicts={
                    JudgeMetricId.DIFFICULTY.value: {
                        "passed": index % 2 == 0,
                        "status": "completed",
                    }
                },
            )
        )
    session.flush()

    curve = curve_from_store(session)
    assert curve["total_reviews"] == 12
    assert curve["points"][0]["reviews"] == 10
    difficulty = curve["points"][0]["judges"][JudgeMetricId.DIFFICULTY.value]
    assert difficulty["n"] >= 1
    assert "agreements" in difficulty
    assert "missed" in difficulty
    assert "false_alarms" in difficulty
