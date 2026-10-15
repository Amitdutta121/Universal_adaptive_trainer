"""Approved tutorial blocks are frozen with a question set (Phase 6, Task 25)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_coverage import _question, _taxonomy
from test_tutorial_pregeneration import _block

from app.coverage import create_question_set
from app.domain.enums import TutorialBlockStatus
from app.persistence.models import TutorialBlockRow
from app.tutorials.approval import decide_recipe


def _frozen(session: Session, set_version_id: int) -> list[TutorialBlockRow]:
    return list(
        session.scalars(
            select(TutorialBlockRow)
            .where(TutorialBlockRow.set_version_id == set_version_id)
            .order_by(TutorialBlockRow.id)
        )
    )


def test_freezing_a_set_snapshots_its_approved_blocks(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id)
    approved = _block(session, subtopic_id, status=TutorialBlockStatus.APPROVED)
    _block(session, subtopic_id, "py.topic_flow")  # draft
    _block(session, subtopic_id, "py.topic_flow", status=TutorialBlockStatus.REJECTED)
    _block(session, subtopic_id, status=TutorialBlockStatus.FAILED)

    row = create_question_set(session, label="Autumn 2026")

    (copy,) = _frozen(session, row.id)
    assert copy.id != approved.id
    assert (copy.recipe_id, copy.guidance_level, copy.payload, copy.chunk_ids) == (
        approved.recipe_id,
        approved.guidance_level,
        approved.payload,
        approved.chunk_ids,
    )
    assert copy.status is TutorialBlockStatus.APPROVED


def test_later_edits_do_not_change_a_frozen_set(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id)
    bank = _block(session, subtopic_id, status=TutorialBlockStatus.APPROVED)
    row = create_question_set(session, label="Autumn 2026")
    (before,) = _frozen(session, row.id)
    snapshot = (before.status, dict(before.payload))

    # Reject the recipe, edit the bank block, approve a new one.
    decide_recipe(
        session, curriculum_version_id=version.id, recipe_id=bank.recipe_id, approved=False
    )
    bank.payload = {"markdown": "rewritten"}
    _block(session, subtopic_id, "py.topic_flow", status=TutorialBlockStatus.APPROVED)
    session.commit()

    session.expire_all()
    (after,) = _frozen(session, row.id)
    assert (after.status, after.payload) == snapshot
    # The next set freezes the bank as it is now.
    later = create_question_set(session, label="Spring 2027")
    assert [b.recipe_id for b in _frozen(session, later.id)] == ["py.topic_flow"]


def test_blocks_of_another_taxonomy_are_not_frozen(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id)
    _, (other_subtopic,) = _taxonomy(session)
    _block(session, other_subtopic, status=TutorialBlockStatus.APPROVED)

    row = create_question_set(session, label="Autumn 2026", curriculum_version_id=version.id)

    assert _frozen(session, row.id) == []
