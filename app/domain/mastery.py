"""Shared mastery, weakness and scoring value objects.

These encode the fixed adaptive-training decisions that both the professor
content pipeline and the student engine must agree on. The engine itself --
roulette selection, BKT updates, weakness updates -- lives behind
``app.adaptive``.

Changes here affect both workflows and should be made deliberately.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import Difficulty, MasteryBand

#: Student question scores are on a 0-100 scale.
MIN_SCORE = 0.0
MAX_SCORE = 100.0

#: All subtopic weaknesses start equal, so the first roulette draw is uniform.
INITIAL_SUBTOPIC_WEAKNESS = 1.0

#: Boundaries on BKT P(known) separating low / medium / high mastery.
LOW_MASTERY_CEILING = 0.45
MEDIUM_MASTERY_CEILING = 0.85


class BKTParameters(BaseModel):
    """Bayesian Knowledge Tracing parameters for one topic."""

    p_init: float = Field(default=0.1, ge=0.0, le=1.0)
    p_learn: float = Field(default=0.03, ge=0.0, le=1.0)
    p_guess: float = Field(default=0.3, ge=0.0, le=1.0)
    p_slip: float = Field(default=0.05, ge=0.0, le=1.0)


DEFAULT_BKT_PARAMETERS = BKTParameters()


def score_from_tests(passed_tests: int, total_tests: int) -> float:
    """Return the 0-100 score for a testable programming question.

    ``passed_tests / total_tests * 100``.

    Raises:
        ValueError: if ``total_tests`` is not positive, or ``passed_tests`` is
            negative or exceeds ``total_tests``.
    """
    if total_tests <= 0:
        raise ValueError("total_tests must be greater than zero")
    if passed_tests < 0:
        raise ValueError("passed_tests cannot be negative")
    if passed_tests > total_tests:
        raise ValueError("passed_tests cannot exceed total_tests")
    return passed_tests / total_tests * MAX_SCORE


def mastery_band(p_known: float) -> MasteryBand:
    """Map a BKT mastery probability onto a coarse band.

    Raises:
        ValueError: if ``p_known`` is outside ``[0, 1]``.
    """
    if not 0.0 <= p_known <= 1.0:
        raise ValueError("p_known must be within [0, 1]")
    if p_known < LOW_MASTERY_CEILING:
        return MasteryBand.LOW
    if p_known < MEDIUM_MASTERY_CEILING:
        return MasteryBand.MEDIUM
    return MasteryBand.HIGH


#: Fixed decision: low mastery -> easy, medium -> medium, high -> hard.
BAND_TO_DIFFICULTY: dict[MasteryBand, Difficulty] = {
    MasteryBand.LOW: Difficulty.EASY,
    MasteryBand.MEDIUM: Difficulty.MEDIUM,
    MasteryBand.HIGH: Difficulty.HARD,
}


def difficulty_for_mastery(p_known: float) -> Difficulty:
    """Return the difficulty a student at mastery ``p_known`` should receive."""
    return BAND_TO_DIFFICULTY[mastery_band(p_known)]
