"""Storage for memory episodes (``memory_episodes``)."""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import QuestionType, ReviewDecision
from app.persistence.models import MemoryEpisodeRow, ProfessorReviewRow, QuestionRow


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
