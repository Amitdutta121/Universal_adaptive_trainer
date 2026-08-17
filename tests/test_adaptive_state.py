"""BKT mastery and subtopic weakness updates (ADR-041)."""

from __future__ import annotations

import pytest

from app.adaptive.state import (
    MIN_SUBTOPIC_WEAKNESS,
    WEAKNESS_LEARNING_RATE,
    evidence_posterior,
    update_mastery,
    update_weakness,
)
from app.domain.enums import Difficulty
from app.domain.mastery import (
    DEFAULT_BKT_PARAMETERS,
    INITIAL_SUBTOPIC_WEAKNESS,
    BKTParameters,
    difficulty_for_mastery,
)


def _transition(posterior: float, params: BKTParameters = DEFAULT_BKT_PARAMETERS) -> float:
    """The learning step, so a test can state the expected value independently."""
    return posterior + (1.0 - posterior) * params.p_learn


class TestEvidencePosterior:
    """The standard BKT evidence step, which the partial-credit blend mixes."""

    def test_a_correct_answer_raises_belief(self) -> None:
        assert evidence_posterior(0.5, correct=True, params=DEFAULT_BKT_PARAMETERS) > 0.5

    def test_a_wrong_answer_lowers_belief(self) -> None:
        assert evidence_posterior(0.5, correct=False, params=DEFAULT_BKT_PARAMETERS) < 0.5

    def test_it_matches_the_textbook_formula(self) -> None:
        params = BKTParameters(p_slip=0.1, p_guess=0.2)
        expected = (0.4 * 0.9) / (0.4 * 0.9 + 0.6 * 0.2)
        assert evidence_posterior(0.4, correct=True, params=params) == pytest.approx(expected)

    def test_an_impossible_observation_leaves_the_prior_alone(self) -> None:
        """No guessing and no knowledge explains a correct answer, so it says nothing."""
        params = BKTParameters(p_guess=0.0)
        assert evidence_posterior(0.0, correct=True, params=params) == 0.0

    @pytest.mark.parametrize("correct", [True, False])
    def test_certainty_is_preserved(self, correct: bool) -> None:
        result = evidence_posterior(1.0, correct=correct, params=DEFAULT_BKT_PARAMETERS)
        assert result == pytest.approx(1.0)


class TestUpdateMastery:
    """A 0-100 score is one partial observation, not a pass/fail."""

    def test_a_perfect_score_reduces_to_standard_bkt(self) -> None:
        prior = 0.3
        expected = _transition(
            evidence_posterior(prior, correct=True, params=DEFAULT_BKT_PARAMETERS)
        )
        assert update_mastery(prior, 100.0) == pytest.approx(expected)

    def test_a_zero_score_reduces_to_standard_bkt(self) -> None:
        prior = 0.3
        expected = _transition(
            evidence_posterior(prior, correct=False, params=DEFAULT_BKT_PARAMETERS)
        )
        assert update_mastery(prior, 0.0) == pytest.approx(expected)

    def test_a_partial_score_lands_between_the_two_ends(self) -> None:
        prior = 0.5
        low = update_mastery(prior, 0.0)
        middle = update_mastery(prior, 70.0)
        high = update_mastery(prior, 100.0)
        assert low < middle < high

    def test_seventy_percent_is_seventy_percent_of_the_way(self) -> None:
        """The blend is linear in the score, which is the point of ADR-041 item 1."""
        prior = 0.5
        low = update_mastery(prior, 0.0)
        high = update_mastery(prior, 100.0)
        assert update_mastery(prior, 70.0) == pytest.approx(low + 0.7 * (high - low))

    def test_there_is_no_cliff_at_a_pass_mark(self) -> None:
        """One test case either side of 60 must not flip the update."""
        just_under = update_mastery(0.5, 59.0)
        just_over = update_mastery(0.5, 61.0)
        assert abs(just_over - just_under) < 0.02

    def test_repeated_success_climbs_toward_certainty(self) -> None:
        p_known = 0.2
        for _ in range(20):
            p_known = update_mastery(p_known, 100.0)
        assert p_known > 0.95
        assert difficulty_for_mastery(p_known) is Difficulty.HARD

    def test_repeated_failure_stays_low(self) -> None:
        p_known = 0.5
        for _ in range(20):
            p_known = update_mastery(p_known, 0.0)
        assert difficulty_for_mastery(p_known) is Difficulty.EASY

    @pytest.mark.parametrize("score", [0.0, 25.0, 50.0, 100.0])
    def test_the_result_is_always_a_probability(self, score: float) -> None:
        for prior in (0.0, 0.5, 1.0):
            assert 0.0 <= update_mastery(prior, score) <= 1.0

    @pytest.mark.parametrize("score", [-1.0, 100.1])
    def test_a_score_outside_the_scale_is_rejected(self, score: float) -> None:
        with pytest.raises(ValueError):
            update_mastery(0.5, score)

    @pytest.mark.parametrize("prior", [-0.01, 1.01])
    def test_a_prior_outside_zero_to_one_is_rejected(self, prior: float) -> None:
        with pytest.raises(ValueError):
            update_mastery(prior, 50.0)


class TestUpdateWeakness:
    """Weakness is the roulette weight, so it moves smoothly and never hits zero."""

    def test_a_perfect_score_lowers_weakness(self) -> None:
        assert update_weakness(INITIAL_SUBTOPIC_WEAKNESS, 100.0) < INITIAL_SUBTOPIC_WEAKNESS

    def test_a_zero_score_holds_weakness_at_the_maximum(self) -> None:
        assert update_weakness(INITIAL_SUBTOPIC_WEAKNESS, 0.0) == INITIAL_SUBTOPIC_WEAKNESS

    def test_a_zero_score_raises_a_lowered_weakness(self) -> None:
        assert update_weakness(0.2, 0.0) > 0.2

    def test_it_moves_by_the_learning_rate(self) -> None:
        expected = 1.0 + WEAKNESS_LEARNING_RATE * (0.0 - 1.0)
        assert update_weakness(1.0, 100.0) == pytest.approx(expected)

    def test_a_mastered_subtopic_stops_at_the_floor(self) -> None:
        weakness = INITIAL_SUBTOPIC_WEAKNESS
        for _ in range(50):
            weakness = update_weakness(weakness, 100.0)
        assert weakness == MIN_SUBTOPIC_WEAKNESS

    def test_the_floor_keeps_a_mastered_subtopic_drawable(self) -> None:
        """Zero weight would remove it from roulette permanently (ADR-041)."""
        assert MIN_SUBTOPIC_WEAKNESS > 0.0

    def test_it_never_exceeds_the_starting_weakness(self) -> None:
        assert update_weakness(INITIAL_SUBTOPIC_WEAKNESS, 0.0) <= INITIAL_SUBTOPIC_WEAKNESS

    def test_a_floored_subtopic_recovers_after_a_failure(self) -> None:
        recovered = update_weakness(MIN_SUBTOPIC_WEAKNESS, 0.0)
        assert recovered > MIN_SUBTOPIC_WEAKNESS

    @pytest.mark.parametrize("score", [-0.5, 101.0])
    def test_a_score_outside_the_scale_is_rejected(self, score: float) -> None:
        with pytest.raises(ValueError):
            update_weakness(0.5, score)

    @pytest.mark.parametrize("weakness", [-0.01, 1.5])
    def test_an_out_of_range_weakness_is_rejected(self, weakness: float) -> None:
        with pytest.raises(ValueError):
            update_weakness(weakness, 50.0)
