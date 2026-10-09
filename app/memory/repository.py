"""Storage for memory episodes (``memory_episodes``) and guidelines (``memory_guidelines``)."""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import GuidelineStatus, QuestionType, ReviewDecision
from app.persistence.models import (
    MemoryEpisodeRow,
    MemoryGuidelineRow,
    ProfessorReviewRow,
    QuestionRow,
)


class MemoryEpisodeRepository:
    """Episodes are written once, when their verdict lands, and never updated."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, episode: MemoryEpisodeRow) -> MemoryEpisodeRow:
        self._session.add(episode)
        self._session.flush()
        return episode

    def get_for_review(self, review_id: int) -> MemoryEpisodeRow | None:
        return self._session.scalar(
            select(MemoryEpisodeRow).where(MemoryEpisodeRow.review_id == review_id)
        )

    def latest_per_question(
        self,
        *,
        subject: str,
        question_type: QuestionType,
        decisions: Collection[ReviewDecision],
        exclude_question_ids: Collection[int] = (),
    ) -> list[tuple[MemoryEpisodeRow, QuestionRow]]:
        """Each question's newest review episode of ``subject`` and type, if its decision is
        one of ``decisions``; newest first, with the question it is about.

        Only episodes whose review and question still exist: a deleted review's episode is
        never returned, even if a bulk delete bypassed the ORM cascade.
        """
        stmt = (
            select(MemoryEpisodeRow, QuestionRow)
            .join(ProfessorReviewRow, MemoryEpisodeRow.review_id == ProfessorReviewRow.id)
            .join(QuestionRow, MemoryEpisodeRow.question_id == QuestionRow.id)
            .where(
                MemoryEpisodeRow.subject == subject,
                MemoryEpisodeRow.question_type == question_type,
            )
            .order_by(MemoryEpisodeRow.created_at.desc(), MemoryEpisodeRow.id.desc())
        )
        if exclude_question_ids:
            stmt = stmt.where(MemoryEpisodeRow.question_id.not_in(exclude_question_ids))
        latest: dict[int, tuple[MemoryEpisodeRow, QuestionRow]] = {}
        for episode, question in self._session.execute(stmt):
            latest.setdefault(episode.question_id, (episode, question))
        return [pair for pair in latest.values() if pair[0].decision in decisions]


class MemoryGuidelineRepository:
    """Guidelines are edited in place by the lesson run and by the professor, never rewritten."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, guideline: MemoryGuidelineRow) -> MemoryGuidelineRow:
        self._session.add(guideline)
        self._session.flush()
        return guideline

    def get(self, guideline_id: int, *, subject: str) -> MemoryGuidelineRow | None:
        """The guideline, only if it belongs to ``subject`` (another course's is not found)."""
        row = self._session.get(MemoryGuidelineRow, guideline_id)
        return row if row is not None and row.subject == subject else None

    def list_for(
        self,
        *,
        subject: str,
        statuses: Collection[GuidelineStatus],
        target: str | None = None,
    ) -> list[MemoryGuidelineRow]:
        """``subject``'s guidelines in ``statuses`` (of ``target`` if given), oldest first."""
        stmt = (
            select(MemoryGuidelineRow)
            .where(
                MemoryGuidelineRow.subject == subject,
                MemoryGuidelineRow.status.in_(list(statuses)),
            )
            .order_by(MemoryGuidelineRow.id)
        )
        if target is not None:
            stmt = stmt.where(MemoryGuidelineRow.target == target)
        return list(self._session.scalars(stmt))

    def citing(self, review_id: int) -> list[MemoryGuidelineRow]:
        """Every guideline, of any subject or status, whose evidence includes ``review_id``."""
        rows = self._session.scalars(
            select(MemoryGuidelineRow).where(
                MemoryGuidelineRow.review_ids.is_not(None),
                MemoryGuidelineRow.status.in_([GuidelineStatus.PENDING, GuidelineStatus.ACTIVE]),
            )
        )
        return [row for row in rows if review_id in (row.review_ids or [])]
