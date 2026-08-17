"""Choosing what to ask next, as pure functions.

Responsibility
    The selection steps that need no database: the weakness-weighted roulette
    draw over subtopics, the order in which one cell's candidate questions
    should be offered, and the order in which difficulties are tried when a cell
    turns out to be empty.

    The queries that produce the weights and the candidates belong to
    :mod:`app.persistence`; assembling them into a served question belongs to
    :mod:`app.adaptive.service`. Keeping the choices here pure is what lets a
    seeded draw be asserted exactly.

Allowed dependencies
    ``app.domain`` only.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.enums import Difficulty


def choose_subtopic(weights: Mapping[int, float], rng: random.Random) -> int:
    """Draw one subtopic id, each weighted by its weakness.

    ``rng`` is injected rather than taken from the module-global generator so a
    run can be reproduced from a recorded seed.

    Raises:
        ValueError: if ``weights`` is empty or holds a negative weight.
    """
    if not weights:
        raise ValueError("choose_subtopic needs at least one subtopic to draw from")

    negative = sorted(subtopic_id for subtopic_id, weight in weights.items() if weight < 0)
    if negative:
        raise ValueError(f"weakness cannot be negative: subtopic(s) {negative}")

    # Sorted so one seed always yields one draw. Dict order here reflects
    # whatever the query happened to return, and a roulette that depended on it
    # could not be reproduced from the seed that produced it.
    ordered = sorted(weights.items())
    total = math.fsum(weight for _, weight in ordered)
    if total <= 0.0:
        # No weakness anywhere, so there is nothing to exploit. Explore
        # uniformly rather than always returning the lowest id.
        return rng.choice([subtopic_id for subtopic_id, _ in ordered])

    threshold = rng.random() * total
    cumulative = 0.0
    for subtopic_id, weight in ordered:
        cumulative += weight
        if threshold < cumulative:
            return subtopic_id
    # Reachable only through floating-point drift in the sum above; the last
    # bucket is the one the threshold fell in.
    return ordered[-1][0]


@dataclass(frozen=True)
class Candidate:
    """One approved question competing to be served for a (subtopic, difficulty) cell."""

    question_id: int
    #: Global bank priority. Lowered to ``LOWEST_PRIORITY`` once served to anyone.
    priority: int
    #: Global serve count, across every student.
    times_used: int
    #: Whether *this* student has already answered it. ADR-041's extension to the
    #: fixed priority rule, and the reason it is not enough to sort on priority.
    answered_by_student: bool = False


def rank_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Order a cell's questions best-first; the head is the one to serve.

    Unseen-by-this-student first (ADR-041), then the fixed rule: highest
    priority, then least used, then lowest id so the order is total and stable.
    Seen questions are ranked rather than filtered out, which is what keeps reuse
    available once the cell's unseen questions run out.
    """
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.answered_by_student,
            -candidate.priority,
            candidate.times_used,
            candidate.question_id,
        ),
    )


#: Difficulty is the cheaper half of the request to compromise, so an empty cell
#: relaxes it before abandoning the subtopic (ADR-041). From ``medium`` the step
#: is down before up: serving a struggling student something too hard is the
#: worse error.
_FALLBACK_ORDER: dict[Difficulty, tuple[Difficulty, ...]] = {
    Difficulty.EASY: (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD),
    Difficulty.MEDIUM: (Difficulty.MEDIUM, Difficulty.EASY, Difficulty.HARD),
    Difficulty.HARD: (Difficulty.HARD, Difficulty.MEDIUM, Difficulty.EASY),
}


def difficulty_fallback_order(preferred: Difficulty) -> tuple[Difficulty, ...]:
    """Difficulties to try for one subtopic, the mastery-derived one first."""
    return _FALLBACK_ORDER[preferred]


__all__ = [
    "Candidate",
    "choose_subtopic",
    "difficulty_fallback_order",
    "rank_candidates",
]
