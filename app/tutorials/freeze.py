"""Freezing approved tutorial blocks with a question set (Phase 6, Task 25).

A frozen set must serve the same tutorials to every student who trains on it, whatever the
professor changes in the bank afterwards. So freezing copies each approved bank block into a
new row pinned to the set (``set_version_id``); the copy is never updated, and approving,
rejecting or regenerating bank blocks later leaves it as it was. Students are only ever served
copies.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import TutorialBlockStatus
from app.persistence.models import QuestionSetVersionRow, TutorialBlockRow
from app.tutorials.approval import subtopic_ids_of


def freeze_blocks(session: Session, set_row: QuestionSetVersionRow) -> int:
    """Copy the taxonomy's approved bank blocks into the set. Returns how many. Flushes."""
    if set_row.curriculum_version_id is None:
        return 0
    approved = session.scalars(
        select(TutorialBlockRow)
        .where(
            TutorialBlockRow.set_version_id.is_(None),
            TutorialBlockRow.status == TutorialBlockStatus.APPROVED,
            TutorialBlockRow.subtopic_id.in_(subtopic_ids_of(set_row.curriculum_version_id)),
        )
        .order_by(TutorialBlockRow.id)
    ).all()
    for block in approved:
        session.add(
            TutorialBlockRow(
                subtopic_id=block.subtopic_id,
                recipe_id=block.recipe_id,
                guidance_level=block.guidance_level,
                renderer=block.renderer,
                payload=dict(block.payload),
                chunk_ids=list(block.chunk_ids),
                status=TutorialBlockStatus.APPROVED,
                model=block.model,
                set_version_id=set_row.id,
            )
        )
    session.flush()
    return len(approved)
