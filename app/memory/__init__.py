"""Memory the generator and the judges learn from (ADR-063, ADR-064).

Responsibility
    Keep **episodes**: reviewed questions with the professor's verdict, reasons, comment and
    corrections, and every judge's verdict at review time (``memory_episodes``), plus the
    failed attempts of approved round questions as retry episodes. Keep
    **guidelines** (semantic memory, ``memory_guidelines``): short rules per target
    (``generator:<type>``; ``judge:<metric>`` in m11), edited by operations the lesson run
    distils from new reviews, active only with two supporting reviews or the professor's
    confirmation, output-contract rules refused.

Key rules
    * Writing an episode makes no model or embedding call. Distilling guidelines is one
      structured call per target, made only by the lesson run.
    * Memory is scoped by subject key (the course's ``personal_key``); one subject's memory is
      never retrieved for another.
    * An episode lives exactly as long as its review; a deleted review stops supporting the
      guidelines it taught.

Allowed dependencies
    ``app.domain``, ``app.errors``, ``app.llm``, ``app.persistence``, ``app.subjects``, and the
    pure text helpers of ``app.retrieval.duplicates``. Must not import ``app.generation`` or
    ``app.feedback``.
"""

from app.memory.episodes import (
    SOURCE_AUDIT,
    SOURCE_BORDERLINE,
    SOURCE_RETRY,
    SOURCE_REVIEW,
    ReviewedQuestion,
    judge_verdicts,
    record_retry_episodes,
    record_review_episode,
    rejection_because,
    retry_lessons,
    snapshot_question,
)
from app.memory.guidelines import (
    ACTIVE_SUPPORT,
    DistillResult,
    GuidelineEdits,
    GuidelineOperation,
    active_guidelines,
    apply_operations,
    confirm_guideline,
    delete_guideline,
    distill_guidelines,
    forget_review,
    generator_target,
    judge_target,
    refusal_reason,
    render_with_guidelines,
)
from app.memory.repository import MemoryEpisodeRepository, MemoryGuidelineRepository

__all__ = [
    "ACTIVE_SUPPORT",
    "SOURCE_AUDIT",
    "SOURCE_BORDERLINE",
    "SOURCE_RETRY",
    "SOURCE_REVIEW",
    "DistillResult",
    "GuidelineEdits",
    "GuidelineOperation",
    "MemoryEpisodeRepository",
    "MemoryGuidelineRepository",
    "ReviewedQuestion",
    "active_guidelines",
    "apply_operations",
    "confirm_guideline",
    "delete_guideline",
    "distill_guidelines",
    "forget_review",
    "generator_target",
    "judge_target",
    "judge_verdicts",
    "record_retry_episodes",
    "record_review_episode",
    "refusal_reason",
    "rejection_because",
    "render_with_guidelines",
    "retry_lessons",
    "snapshot_question",
]
