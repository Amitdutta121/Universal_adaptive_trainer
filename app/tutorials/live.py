"""Live tutorials: no approval step, and a block a student needs is written on demand.

With ``tutorials_live`` on, a run is served from the course's bank -- every block that is
neither ``failed`` nor ``rejected``, reviewed or not -- instead of the copies frozen with its
question set (``app/tutorials/freeze.py``). Rejecting a recipe for a taxonomy still hides its
blocks, so a professor's decision now means "don't use this recipe" rather than "may be shown".
Which blocks each student saw stays logged per attempt (``tutorial_block_views``).

When the moment wants a guidance level the bank holds fewer than ``BLOCK_COUNT`` blocks of,
one more is planned: the best-fitting recipe written at that level that has no block for the
subtopic yet, is not rejected, and was not asked for in the last ``RETRY_AFTER`` (so a block
that failed, or a subtopic without book text, is not retried on every answer). It is written by
the pre-generation job -- one block, ``request["live"]`` -- after the response is sent: the
student sees what the bank has now, and the block is there for their next answer and for the
next student. A course gets at most ``tutorials_live_daily_cap`` live jobs per 24 hours.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import GuidanceLevel, JobKind, TutorialBlockStatus
from app.jobs.queue import JobQueue
from app.jobs.runner import create_job
from app.llm import StructuredLLMClient
from app.persistence.models import BackgroundJobRow, TutorialBlockRow
from app.retrieval.embedder import Embedder
from app.tutorials.approval import decisions
from app.tutorials.composer import BLOCK_COUNT, fit_rank
from app.tutorials.jobs import PlannedBlock, run_pregeneration
from app.tutorials.schema import ContentKind, TutorialRecipe

#: The statuses a live run is served from: written and checked, whether reviewed or not.
SERVABLE = (TutorialBlockStatus.DRAFT, TutorialBlockStatus.APPROVED)
#: How long a block asked for is not asked for again, whatever came of it.
RETRY_AFTER = timedelta(hours=6)
#: The window the daily cap counts over.
CAP_WINDOW = timedelta(hours=24)
#: Recent jobs read to find the live ones; far more than a day's cap.
_RECENT_JOBS = 1000


@dataclass(frozen=True)
class LiveQueue:
    """Where a live block's job is submitted; ``client``/``embedder`` are test seams."""

    queue: JobQueue
    client: StructuredLLMClient | None = None
    embedder: Embedder | None = None


def bank_blocks(session: Session, subtopic_id: int) -> list[TutorialBlockRow]:
    """The subtopic's servable bank blocks (not the copies frozen with a set)."""
    return list(
        session.scalars(
            select(TutorialBlockRow)
            .where(
                TutorialBlockRow.set_version_id.is_(None),
                TutorialBlockRow.subtopic_id == subtopic_id,
                TutorialBlockRow.status.in_(SERVABLE),
            )
            .order_by(TutorialBlockRow.id)
        )
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def recent_live_jobs(session: Session, course_id: int | None) -> list[BackgroundJobRow]:
    """The course's live jobs created in the last ``CAP_WINDOW``, newest first."""
    jobs = session.scalars(
        select(BackgroundJobRow)
        .where(
            BackgroundJobRow.kind == JobKind.TUTORIAL_PREGENERATION,
            BackgroundJobRow.course_id.is_(None)
            if course_id is None
            else BackgroundJobRow.course_id == course_id,
        )
        .order_by(BackgroundJobRow.id.desc())
        .limit(_RECENT_JOBS)
    ).all()
    since = datetime.now(UTC) - CAP_WINDOW
    return [
        job for job in jobs if (job.request or {}).get("live") and _aware(job.created_at) >= since
    ]


def plan_live_block(
    session: Session,
    *,
    course_id: int | None,
    curriculum_version_id: int,
    subtopic_id: int,
    level: GuidanceLevel,
    kinds: Sequence[ContentKind],
    recipes: Mapping[str, TutorialRecipe],
    bank: Sequence[TutorialBlockRow],
) -> PlannedBlock | None:
    """The one block to write for this moment, or ``None`` when nothing should be written."""
    at_level = [b for b in bank if b.guidance_level == level]
    if len(at_level) >= BLOCK_COUNT[level]:
        return None
    made = {b.recipe_id for b in at_level}
    recent = recent_live_jobs(session, course_id)
    if len(recent) >= get_settings().tutorials_live_daily_cap:
        return None
    retry_from = datetime.now(UTC) - RETRY_AFTER
    asked = {
        (p["subtopic_id"], p["recipe_id"], p["guidance_level"])
        for job in recent
        if _aware(job.created_at) >= retry_from
        for p in job.request.get("planned", [])
    }
    rejected = {
        recipe_id
        for recipe_id, approved in decisions(session, curriculum_version_id).items()
        if not approved
    }
    candidates = [
        recipe
        for recipe in recipes.values()
        if level in recipe.guidance_levels
        and recipe.id not in made
        and recipe.id not in rejected
        and (subtopic_id, recipe.id, level.value) not in asked
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda r: (fit_rank(r, kinds), r.id))
    return PlannedBlock(subtopic_id, best.id, level)


def queue_live_block(
    session: Session,
    planned: PlannedBlock,
    *,
    course_id: int | None,
    curriculum_version_id: int,
    live: LiveQueue,
) -> BackgroundJobRow:
    """Add the one-block job (flushed; the caller's commit saves it) and hand it to the queue,
    which runs it after the response."""
    job = create_job(
        session,
        kind=JobKind.TUTORIAL_PREGENERATION,
        title=f"Live tutorial block · {planned.recipe_id} · {planned.guidance_level.value}",
        total=1,
        request={
            "curriculum_version_id": curriculum_version_id,
            "planned": [
                {
                    "subtopic_id": planned.subtopic_id,
                    "recipe_id": planned.recipe_id,
                    "guidance_level": planned.guidance_level.value,
                }
            ],
            "live": True,
        },
        course_id=course_id,
    )
    live.queue.submit(run_pregeneration, job.id, client=live.client, embedder=live.embedder)
    return job
