"""Memory the generator and the judges learn from (ADR-063, ADR-064).

Responsibility
    Keep **episodes**: reviewed questions with the professor's verdict, reasons, comment and
    corrections, and every judge's verdict at review time (``memory_episodes``). Guidelines
    (semantic memory) arrive in m5.

Key rules
    * Writing an episode makes no model or embedding call.
    * Episodes are scoped by subject key (the course's ``personal_key``); one subject's
      memory is never retrieved for another.
    * An episode lives exactly as long as its review.

Allowed dependencies
    ``app.domain``, ``app.persistence``, ``app.subjects``, and the pure text helpers of
    ``app.retrieval.duplicates``. Must not import ``app.generation`` or ``app.feedback``.
"""

from app.memory.episodes import (
    SOURCE_REVIEW,
    ReviewedQuestion,
    judge_verdicts,
    record_review_episode,
    rejection_because,
    snapshot_question,
)
from app.memory.repository import MemoryEpisodeRepository

__all__ = [
    "SOURCE_REVIEW",
    "MemoryEpisodeRepository",
    "ReviewedQuestion",
    "judge_verdicts",
    "record_review_episode",
    "rejection_because",
    "snapshot_question",
]
