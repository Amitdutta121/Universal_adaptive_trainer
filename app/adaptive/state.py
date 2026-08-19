"""The two state transitions of the student loop, as pure functions.

Responsibility
    What one score does to a topic's BKT mastery, and what it does to a
    subtopic's weakness. No IO, no session, no repository: the engine in
    :mod:`app.adaptive.service` supplies the stored values and writes the
    results back.

The mechanism is fixed by ``CLAUDE.md``. The two constants it leaves open --
how fast weakness moves, and how far down it may go -- are decided in ADR-041
and live here rather than in :mod:`app.domain.mastery`, which owns the values
both loops share and says that the updates themselves belong to this package.

Argument violations raise :class:`ValueError`, matching
:func:`app.domain.mastery.score_from_tests` next door. Translating those into an
:class:`~app.errors.AdaptiveTrainerError` is the service's job, at the request
boundary where there is a response to render.

Allowed dependencies
    ``app.domain`` only.
"""

from __future__ import annotations

from app.domain.mastery import (
    DEFAULT_BKT_PARAMETERS,
    INITIAL_SUBTOPIC_WEAKNESS,
    MAX_SCORE,
    MIN_SCORE,
    BKTParameters,
)

#: How far a single score moves a subtopic's weakness toward what it implies.
#: 0.15 keeps the focus responsive without letting one answer swing the roulette
#: too abruptly.
WEAKNESS_LEARNING_RATE = 0.15

#: Weakness is the roulette weight, so zero would remove a subtopic from
#: selection permanently. The floor keeps a mastered subtopic reachable while
#: still making genuinely weak areas much more likely.
MIN_SUBTOPIC_WEAKNESS = 0.05


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _require_score(score: float) -> None:
    if not MIN_SCORE <= score <= MAX_SCORE:
        raise ValueError(f"score must be within [{MIN_SCORE}, {MAX_SCORE}]")


def _require_probability(p_known: float) -> None:
    if not 0.0 <= p_known <= 1.0:
        raise ValueError("p_known must be within [0, 1]")


def evidence_posterior(p_known: float, *, correct: bool, params: BKTParameters) -> float:
    """P(knows the skill) after one binary observation, before any learning.

    The standard BKT evidence step. Exposed because the partial-credit blend in
    :func:`update_mastery` is defined as a mixture of its two outcomes, and a
    test that cannot see both ends cannot show the blend reduces to them.
    """
    if correct:
        likely_known = p_known * (1.0 - params.p_slip)
        likely_unknown = (1.0 - p_known) * params.p_guess
    else:
        likely_known = p_known * params.p_slip
        likely_unknown = (1.0 - p_known) * (1.0 - params.p_guess)

    total = likely_known + likely_unknown
    if total <= 0.0:
        # Both explanations of this observation have probability zero -- e.g. a
        # correct answer with p_guess = 0 from a student the model is certain
        # does not know the skill. There is no posterior to compute, and the
        # honest reading of an impossible observation is that it says nothing.
        return p_known
    return likely_known / total


def update_mastery(
    p_known: float,
    score: float,
    params: BKTParameters = DEFAULT_BKT_PARAMETERS,
) -> float:
    """Return the topic's mastery after one 0-100 score (ADR-041).

    The score is treated as a partial observation: the posteriors for a correct
    and an incorrect answer are blended by ``score / 100``, then the single
    learning transition is applied. At 0 and at 100 this is exactly standard
    BKT.

    Raises:
        ValueError: if ``p_known`` is outside ``[0, 1]`` or ``score`` is outside
            ``[0, 100]``.
    """
    _require_probability(p_known)
    _require_score(score)

    fraction = score / MAX_SCORE
    knew_it = evidence_posterior(p_known, correct=True, params=params)
    did_not = evidence_posterior(p_known, correct=False, params=params)

    # One blended observation, then one opportunity to learn. The transition is
    # affine in the posterior, so blending after it would give the same number;
    # blending first is what the sentence above actually describes.
    posterior = fraction * knew_it + (1.0 - fraction) * did_not
    learned = posterior + (1.0 - posterior) * params.p_learn
    return _clamp(learned, 0.0, 1.0)


def update_weakness(weakness: float, score: float) -> float:
    """Return a subtopic's weakness after one 0-100 score (ADR-041).

    A moving average toward what the score implies -- 0 for a perfect answer, 1
    for a zero -- floored at :data:`MIN_SUBTOPIC_WEAKNESS` so a mastered subtopic
    keeps a small chance of being drawn again.

    Raises:
        ValueError: if ``weakness`` is outside ``[0, INITIAL_SUBTOPIC_WEAKNESS]``
            or ``score`` is outside ``[0, 100]``.
    """
    _require_score(score)
    if not 0.0 <= weakness <= INITIAL_SUBTOPIC_WEAKNESS:
        raise ValueError(f"weakness must be within [0, {INITIAL_SUBTOPIC_WEAKNESS}]")

    implied = 1.0 - score / MAX_SCORE
    moved = weakness + WEAKNESS_LEARNING_RATE * (implied - weakness)
    return _clamp(moved, MIN_SUBTOPIC_WEAKNESS, INITIAL_SUBTOPIC_WEAKNESS)


__all__ = [
    "MIN_SUBTOPIC_WEAKNESS",
    "WEAKNESS_LEARNING_RATE",
    "evidence_posterior",
    "update_mastery",
    "update_weakness",
]
