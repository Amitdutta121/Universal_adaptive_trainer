"""Weakness-weighted roulette and candidate ordering (ADR-041)."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from app.adaptive.selection import (
    Candidate,
    choose_subtopic,
    difficulty_fallback_order,
    rank_candidates,
)
from app.domain.enums import Difficulty


class TestChooseSubtopic:
    """Exploitation of weak areas, with exploration retained."""

    def test_a_single_subtopic_is_always_drawn(self) -> None:
        assert choose_subtopic({7: 1.0}, random.Random(0)) == 7

    def test_the_same_seed_gives_the_same_draw(self) -> None:
        weights = {1: 1.0, 2: 1.0, 3: 1.0}
        first = choose_subtopic(weights, random.Random(1234))
        second = choose_subtopic(weights, random.Random(1234))
        assert first == second

    def test_the_draw_does_not_depend_on_dict_order(self) -> None:
        """A recorded seed must reproduce a run whatever order the query returned."""
        ascending = {1: 0.2, 2: 0.5, 3: 0.9}
        descending = {3: 0.9, 2: 0.5, 1: 0.2}
        for seed in range(25):
            assert choose_subtopic(ascending, random.Random(seed)) == choose_subtopic(
                descending, random.Random(seed)
            )

    def test_a_weaker_subtopic_is_drawn_more_often(self) -> None:
        rng = random.Random(99)
        weights = {1: 9.0, 2: 1.0}
        drawn = Counter(choose_subtopic(weights, rng) for _ in range(2000))
        assert drawn[1] > drawn[2] * 4

    def test_a_near_mastered_subtopic_is_still_reachable(self) -> None:
        """The weakness floor exists so exploration survives mastery."""
        rng = random.Random(7)
        weights = {1: 1.0, 2: 0.05}
        drawn = Counter(choose_subtopic(weights, rng) for _ in range(4000))
        assert drawn[2] > 0

    def test_frequencies_track_the_weights(self) -> None:
        rng = random.Random(2024)
        weights = {1: 1.0, 2: 3.0}
        draws = 6000
        drawn = Counter(choose_subtopic(weights, rng) for _ in range(draws))
        assert drawn[2] / draws == pytest.approx(0.75, abs=0.03)

    def test_all_zero_weights_explore_uniformly(self) -> None:
        rng = random.Random(5)
        drawn = Counter(choose_subtopic({1: 0.0, 2: 0.0}, rng) for _ in range(400))
        assert drawn[1] > 0 and drawn[2] > 0

    def test_no_subtopics_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            choose_subtopic({}, random.Random(0))

    def test_a_negative_weakness_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            choose_subtopic({1: 1.0, 2: -0.5}, random.Random(0))


class TestRankCandidates:
    """The fixed priority rule, with ADR-041's per-student key above it."""

    def test_the_highest_priority_question_is_served_first(self) -> None:
        ranked = rank_candidates(
            [
                Candidate(question_id=1, priority=0, times_used=1),
                Candidate(question_id=2, priority=100, times_used=0),
            ]
        )
        assert [candidate.question_id for candidate in ranked] == [2, 1]

    def test_a_used_question_sinks_behind_an_unused_one(self) -> None:
        """A served question drops to LOWEST_PRIORITY, so another is preferred."""
        ranked = rank_candidates(
            [
                Candidate(question_id=1, priority=0, times_used=3),
                Candidate(question_id=2, priority=0, times_used=1),
            ]
        )
        assert ranked[0].question_id == 2

    def test_an_unseen_question_beats_a_higher_priority_seen_one(self) -> None:
        """Student A's usage must not hand student B a repeat (ADR-041 item 3)."""
        ranked = rank_candidates(
            [
                Candidate(question_id=1, priority=100, times_used=0, answered_by_student=True),
                Candidate(question_id=2, priority=0, times_used=5, answered_by_student=False),
            ]
        )
        assert ranked[0].question_id == 2

    def test_seen_questions_remain_available_for_reuse(self) -> None:
        """Ranked, not filtered: an exhausted cell still yields a question."""
        ranked = rank_candidates(
            [
                Candidate(question_id=1, priority=0, times_used=2, answered_by_student=True),
                Candidate(question_id=2, priority=0, times_used=1, answered_by_student=True),
            ]
        )
        assert [candidate.question_id for candidate in ranked] == [2, 1]

    def test_the_order_is_total_and_stable(self) -> None:
        tied = [
            Candidate(question_id=9, priority=50, times_used=0),
            Candidate(question_id=4, priority=50, times_used=0),
        ]
        assert [candidate.question_id for candidate in rank_candidates(tied)] == [4, 9]
        assert [candidate.question_id for candidate in rank_candidates(tied[::-1])] == [4, 9]

    def test_an_empty_cell_ranks_to_nothing(self) -> None:
        assert rank_candidates([]) == []

    def test_the_input_is_not_mutated(self) -> None:
        candidates = [
            Candidate(question_id=1, priority=0, times_used=0),
            Candidate(question_id=2, priority=100, times_used=0),
        ]
        rank_candidates(candidates)
        assert [candidate.question_id for candidate in candidates] == [1, 2]


class TestDifficultyFallbackOrder:
    """An empty cell relaxes difficulty before it abandons the subtopic."""

    @pytest.mark.parametrize("preferred", list(Difficulty))
    def test_the_requested_difficulty_is_tried_first(self, preferred: Difficulty) -> None:
        assert difficulty_fallback_order(preferred)[0] is preferred

    @pytest.mark.parametrize("preferred", list(Difficulty))
    def test_every_difficulty_is_offered_exactly_once(self, preferred: Difficulty) -> None:
        order = difficulty_fallback_order(preferred)
        assert sorted(order, key=list(Difficulty).index) == list(Difficulty)

    def test_medium_steps_down_before_it_steps_up(self) -> None:
        """Too hard for a struggling student is the worse error (ADR-041)."""
        assert difficulty_fallback_order(Difficulty.MEDIUM) == (
            Difficulty.MEDIUM,
            Difficulty.EASY,
            Difficulty.HARD,
        )

    def test_the_ends_step_to_the_nearest_band(self) -> None:
        assert difficulty_fallback_order(Difficulty.EASY)[1] is Difficulty.MEDIUM
        assert difficulty_fallback_order(Difficulty.HARD)[1] is Difficulty.MEDIUM
