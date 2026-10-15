"""The tutorial composer (Phase 6, Task 26)."""

from __future__ import annotations

import random

import pytest
from sqlalchemy.orm import Session
from test_coverage import _question, _taxonomy
from test_tutorial_pregeneration import _block

from app.coverage import create_question_set
from app.domain.enums import GuidanceLevel, TutorialBlockStatus, TutorialRenderer
from app.persistence.models import TutorialBlockRow
from app.tutorials.composer import (
    BLOCK_COUNT,
    ComposeState,
    compose,
    frozen_blocks,
    guidance_for,
)
from app.tutorials.generator import get_recipes
from app.tutorials.schema import ContentKind

RECIPES = {recipe.id: recipe for recipe in get_recipes("intro_python")}
CODE_FIRST = [ContentKind.CODE, ContentKind.MISCONCEPTION, ContentKind.PROCESS, ContentKind.CONCEPT]


def _bank(per_cell: int = 3, seed: int = 0, *, exact: bool = False) -> list[TutorialBlockRow]:
    """Up to ``per_cell`` blocks (exactly, with ``exact``) of every recipe at every level it
    supports, as unsaved rows."""
    rng = random.Random(seed)
    blocks = []
    next_id = 1
    for recipe in RECIPES.values():
        for level in recipe.guidance_levels:
            for _ in range(per_cell if exact else rng.randint(0, per_cell)):
                blocks.append(
                    TutorialBlockRow(
                        id=next_id,
                        subtopic_id=1,
                        recipe_id=recipe.id,
                        guidance_level=level,
                        renderer=recipe.renderer,
                        payload={},
                        chunk_ids=["c"],
                        status=TutorialBlockStatus.APPROVED,
                    )
                )
                next_id += 1
    return blocks


def _state(mastery: float, last_correct: bool | None = True, seed: str = "s") -> ComposeState:
    return ComposeState(
        mastery=mastery, last_correct=last_correct, content_kinds=CODE_FIRST, seed=seed
    )


def test_the_same_seed_and_state_give_the_same_blocks() -> None:
    bank = _bank()
    first = [b.id for b in compose(bank, RECIPES, _state(0.2, seed="run:7"))]
    again = [b.id for b in compose(list(reversed(bank)), RECIPES, _state(0.2, seed="run:7"))]
    assert first == again
    assert len(first) == BLOCK_COUNT[GuidanceLevel.WORKED]


def test_another_seed_can_choose_other_blocks() -> None:
    bank = _bank(per_cell=3, seed=1)
    choices = {
        tuple(b.id for b in compose(bank, RECIPES, _state(0.2, seed=str(n)))) for n in range(20)
    }
    assert len(choices) > 1


@pytest.mark.parametrize("bank_seed", range(25))
def test_fewer_blocks_as_mastery_rises(bank_seed: int) -> None:
    """Property: over any bank and seed, the block count never rises with mastery, and the
    guidance never gets heavier."""
    bank = _bank(seed=bank_seed)
    weight = {GuidanceLevel.WORKED: 2, GuidanceLevel.FADED: 1, GuidanceLevel.CUE: 0}
    for last_correct in (True, None):
        counts, heaviest = [], []
        for step in range(0, 101, 2):
            picked = compose(bank, RECIPES, _state(step / 100, last_correct, f"{bank_seed}"))
            counts.append(len(picked))
            heaviest.append(max((weight[b.guidance_level] for b in picked), default=-1))
        assert counts == sorted(counts, reverse=True), counts
        assert heaviest == sorted(heaviest, reverse=True), heaviest


def test_the_guidance_follows_the_mastery_band() -> None:
    assert guidance_for(0.1, True) is GuidanceLevel.WORKED
    assert guidance_for(0.6, True) is GuidanceLevel.FADED
    assert guidance_for(0.9, True) is GuidanceLevel.CUE
    assert guidance_for(0.99, True) is None
    # A wrong answer is worked through, whatever the mastery.
    assert guidance_for(0.9, False) is GuidanceLevel.WORKED


def test_formats_are_chosen_by_fit_with_the_content() -> None:
    bank = _bank(per_cell=2, exact=True)
    code_first = compose(bank, RECIPES, _state(0.2))
    assert code_first[0].recipe_id == "py.code_trace_stepper"  # fits code
    concept_first = ComposeState(
        mastery=0.2,
        last_correct=None,
        content_kinds=[ContentKind.MISCONCEPTION, ContentKind.CONCEPT],
        seed="s",
    )
    assert compose(bank, RECIPES, concept_first)[0].recipe_id == "py.misconception_line"


def test_one_recipe_does_not_fill_the_card() -> None:
    bank = _bank(per_cell=4, seed=5)
    recipes = [b.recipe_id for b in compose(bank, RECIPES, _state(0.2))]
    assert len(set(recipes)) > 1


def test_a_missing_level_falls_back_to_more_guidance_never_less() -> None:
    worked_only = [b for b in _bank(per_cell=2, seed=2) if b.guidance_level == "worked"]
    picked = compose(worked_only, RECIPES, _state(0.9))
    assert picked and all(b.guidance_level == GuidanceLevel.WORKED for b in picked)
    assert len(picked) == BLOCK_COUNT[GuidanceLevel.CUE]
    cue_only = [b for b in _bank(per_cell=2, seed=2) if b.guidance_level == "cue"]
    assert compose(cue_only, RECIPES, _state(0.2)) == []


def test_an_empty_bank_composes_nothing() -> None:
    assert compose([], RECIPES, _state(0.2, last_correct=False)) == []


def test_only_blocks_frozen_with_the_set_are_read(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id)
    _block(session, subtopic_id, status=TutorialBlockStatus.APPROVED)
    row = create_question_set(session, label="Autumn")
    _block(session, subtopic_id, "py.topic_flow", status=TutorialBlockStatus.APPROVED)

    frozen = frozen_blocks(session, row.id, subtopic_id)

    assert [(b.recipe_id, b.set_version_id) for b in frozen] == [("py.misconception_line", row.id)]
    assert all(b.renderer is TutorialRenderer.MARKDOWN for b in frozen)


def test_a_recipe_weighted_zero_is_never_chosen() -> None:
    bank = _bank(per_cell=2, exact=True)
    state = ComposeState(
        mastery=0.2,
        last_correct=False,
        content_kinds=CODE_FIRST,
        seed="s",
        weights={"py.code_trace_stepper": 0.0},
    )
    picked = compose(bank, RECIPES, state)
    assert picked
    assert "py.code_trace_stepper" not in {b.recipe_id for b in picked}


def test_between_equal_fits_the_heavier_recipe_comes_first() -> None:
    bank = _bank(per_cell=1, exact=True)
    kinds = [ContentKind.CONCEPT]  # misconception_line and topic_flow both fit it
    for heavy, light in [
        ("py.topic_flow", "py.misconception_line"),
        ("py.misconception_line", "py.topic_flow"),
    ]:
        state = ComposeState(
            mastery=0.6,
            last_correct=True,
            content_kinds=kinds,
            seed="s",
            weights={heavy: 1.8, light: 0.6},
        )
        assert compose(bank, RECIPES, state)[0].recipe_id == heavy
