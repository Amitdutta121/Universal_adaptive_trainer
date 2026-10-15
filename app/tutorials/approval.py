"""Approving tutorial blocks by recipe (Phase 6, Task 24).

A professor views a sample of a recipe's blocks and approves or rejects the recipe for one
taxonomy, not block by block. The decision is stored, every bank block of the recipe in that
taxonomy takes its status (``APPROVED`` or ``REJECTED``; a rejected block is hidden), and a
block generated afterwards starts with it. Failed blocks and blocks already frozen with a
question set never change.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.enums import TutorialBlockStatus
from app.persistence.models import (
    SubtopicRow,
    TopicRow,
    TutorialBlockRow,
    TutorialRecipeDecisionRow,
)

#: The statuses a decision moves between; ``FAILED`` blocks have nothing to approve.
_DECIDABLE = (TutorialBlockStatus.DRAFT, TutorialBlockStatus.APPROVED, TutorialBlockStatus.REJECTED)


def subtopic_ids_of(curriculum_version_id: int):
    """A subquery of the taxonomy's subtopic ids."""
    return (
        select(SubtopicRow.id)
        .join(TopicRow, TopicRow.id == SubtopicRow.topic_id)
        .where(TopicRow.curriculum_version_id == curriculum_version_id)
    )


def decide_recipe(
    session: Session, *, curriculum_version_id: int, recipe_id: str, approved: bool
) -> int:
    """Record the decision and apply it to the recipe's bank blocks. Returns how many changed.

    Flushes, does not commit.
    """
    row = session.scalar(
        select(TutorialRecipeDecisionRow).where(
            TutorialRecipeDecisionRow.curriculum_version_id == curriculum_version_id,
            TutorialRecipeDecisionRow.recipe_id == recipe_id,
        )
    )
    if row is None:
        row = TutorialRecipeDecisionRow(
            curriculum_version_id=curriculum_version_id, recipe_id=recipe_id, approved=approved
        )
        session.add(row)
    row.approved = approved
    status = TutorialBlockStatus.APPROVED if approved else TutorialBlockStatus.REJECTED
    changed = session.execute(
        update(TutorialBlockRow)
        .where(
            TutorialBlockRow.recipe_id == recipe_id,
            TutorialBlockRow.set_version_id.is_(None),
            TutorialBlockRow.status.in_(_DECIDABLE),
            TutorialBlockRow.status != status,
            TutorialBlockRow.subtopic_id.in_(subtopic_ids_of(curriculum_version_id)),
        )
        .values(status=status)
        .execution_options(synchronize_session="fetch")
    )
    session.flush()
    return changed.rowcount


def decisions(session: Session, curriculum_version_id: int) -> dict[str, bool]:
    """``recipe_id -> approved`` for every recipe decided in the taxonomy."""
    return dict(
        session.execute(
            select(TutorialRecipeDecisionRow.recipe_id, TutorialRecipeDecisionRow.approved).where(
                TutorialRecipeDecisionRow.curriculum_version_id == curriculum_version_id
            )
        ).all()
    )


def initial_status(
    session: Session, curriculum_version_id: int, recipe_id: str
) -> TutorialBlockStatus:
    """The status a new, valid block of the recipe starts in: its recipe's decision, if any."""
    approved = decisions(session, curriculum_version_id).get(recipe_id)
    if approved is None:
        return TutorialBlockStatus.DRAFT
    return TutorialBlockStatus.APPROVED if approved else TutorialBlockStatus.REJECTED
