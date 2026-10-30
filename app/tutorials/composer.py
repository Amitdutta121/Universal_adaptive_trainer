"""Choosing the tutorial blocks a student sees (Phase 6, Task 26).

How much guidance follows BKT mastery: a wrong answer or low mastery gets ``worked`` blocks
(up to four), medium mastery ``faded`` (two), high mastery one ``cue`` -- and none once the
topic is all but known. Which formats follow the moment's content: each block's recipe is
ranked by how early its ``fits`` appear in the content kinds the caller names (a wrong code
answer puts ``code`` first), and the picks go round the recipes so one recipe does not fill
the card.

Only approved blocks frozen with the student's question set are served (Task 25), and the
choice is seeded: the same seed and state always give the same blocks. :func:`compose` is pure;
:func:`frozen_blocks` reads its input.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import GuidanceLevel, MasteryBand, TutorialBlockStatus
from app.domain.mastery import mastery_band
from app.persistence.models import TutorialBlockRow
from app.tutorials.schema import ContentKind, TutorialRecipe

#: Above this mastery the student is shown nothing: the topic is all but known.
NOTHING_ABOVE = 0.95

#: Blocks shown at each level.
BLOCK_COUNT = {GuidanceLevel.WORKED: 4, GuidanceLevel.FADED: 2, GuidanceLevel.CUE: 1}

#: Levels to fall back to, in order, when the bank has none at the chosen one: more guidance,
#: never less.
_FALLBACK = {
    GuidanceLevel.WORKED: (GuidanceLevel.WORKED,),
    GuidanceLevel.FADED: (GuidanceLevel.FADED, GuidanceLevel.WORKED),
    GuidanceLevel.CUE: (GuidanceLevel.CUE, GuidanceLevel.FADED, GuidanceLevel.WORKED),
}


@dataclass(frozen=True)
class ComposeState:
    """What the composer decides from."""

    #: BKT mastery of the subtopic's topic.
    mastery: float
    #: The answer just given; ``None`` before the first question (pre-teaching).
    last_correct: bool | None
    #: What the moment is about, most relevant first; ranks recipes by their ``fits``.
    content_kinds: Sequence[ContentKind]
    #: Same seed and state -> same blocks.
    seed: str
    #: ``recipe_id -> weight`` from per-recipe stats (Task 28); missing means 1.0, and a
    #: recipe at 0 is never chosen.
    weights: Mapping[str, float] = field(default_factory=dict)


def guidance_for(mastery: float, last_correct: bool | None) -> GuidanceLevel | None:
    """The level to teach at, or ``None`` when nothing should be shown."""
    if last_correct is False:
        return GuidanceLevel.WORKED
    band = mastery_band(mastery)
    if band is MasteryBand.LOW:
        return GuidanceLevel.WORKED
    if band is MasteryBand.MEDIUM:
        return GuidanceLevel.FADED
    return None if mastery >= NOTHING_ABOVE else GuidanceLevel.CUE


def fit_rank(recipe: TutorialRecipe, kinds: Sequence[ContentKind]) -> int:
    """How early the recipe's ``fits`` come in ``kinds``; lower is a better fit."""
    ranks = [list(kinds).index(kind) for kind in recipe.fits if kind in kinds]
    return min(ranks, default=len(kinds))


def compose(
    blocks: Sequence[TutorialBlockRow],
    recipes: Mapping[str, TutorialRecipe],
    state: ComposeState,
) -> list[TutorialBlockRow]:
    """The blocks to show, in order; ``[]`` when none fits or none is wanted."""
    level = guidance_for(state.mastery, state.last_correct)
    if level is None:
        return []
    usable = [
        b for b in blocks if b.recipe_id in recipes and state.weights.get(b.recipe_id, 1.0) > 0
    ]
    shown = _counts(usable)[level]
    for candidate_level in _FALLBACK[level]:
        at_level = [b for b in usable if b.guidance_level == candidate_level]
        if at_level:
            return _pick(at_level, recipes, state, shown)
    return []


def _counts(blocks: Sequence[TutorialBlockRow]) -> dict[GuidanceLevel, int]:
    """How many blocks each level shows from this bank.

    A level shows ``BLOCK_COUNT`` blocks or as many as it (or its fallback) has -- but never
    more than the next heavier level shows, so a sparse bank cannot give a stronger student
    more to read than a weaker one.
    """
    counts: dict[GuidanceLevel, int] = {}
    ceiling = BLOCK_COUNT[GuidanceLevel.WORKED]
    for level in (GuidanceLevel.WORKED, GuidanceLevel.FADED, GuidanceLevel.CUE):
        available = 0
        for fallback in _FALLBACK[level]:
            available = sum(1 for b in blocks if b.guidance_level == fallback)
            if available:
                break
        ceiling = min(BLOCK_COUNT[level], available, ceiling)
        counts[level] = ceiling
    return counts


def _pick(
    blocks: Sequence[TutorialBlockRow],
    recipes: Mapping[str, TutorialRecipe],
    state: ComposeState,
    count: int,
) -> list[TutorialBlockRow]:
    rng = random.Random(state.seed)
    by_recipe: dict[str, list[TutorialBlockRow]] = defaultdict(list)
    for block in sorted(blocks, key=lambda b: b.id):
        by_recipe[block.recipe_id].append(block)
    for group in by_recipe.values():
        rng.shuffle(group)
    # Better fit first, then heavier weight; the seeded tiebreak keeps it deterministic.
    tiebreak = {recipe_id: rng.random() for recipe_id in sorted(by_recipe)}
    order = sorted(
        by_recipe,
        key=lambda r: (
            fit_rank(recipes[r], state.content_kinds),
            -state.weights.get(r, 1.0),
            tiebreak[r],
        ),
    )
    picked: list[TutorialBlockRow] = []
    while len(picked) < count and any(by_recipe[r] for r in order):
        for recipe_id in order:
            if by_recipe[recipe_id] and len(picked) < count:
                picked.append(by_recipe[recipe_id].pop(0))
    return picked


def frozen_blocks(
    session: Session, set_version_id: int, subtopic_id: int
) -> list[TutorialBlockRow]:
    """The approved blocks frozen with the set for one subtopic."""
    return list(
        session.scalars(
            select(TutorialBlockRow)
            .where(
                TutorialBlockRow.set_version_id == set_version_id,
                TutorialBlockRow.subtopic_id == subtopic_id,
                TutorialBlockRow.status == TutorialBlockStatus.APPROVED,
            )
            .order_by(TutorialBlockRow.id)
        )
    )
