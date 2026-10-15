"""Pre-generating a taxonomy's tutorial blocks as one background job (Phase 6, Task 24).

The plan is every subtopic x recipe x guidance level the recipe is written at, minus what the
bank already holds (a block that is not ``failed``), so running it again only fills what is
missing. A dry run prices it -- one call per block, plus at most one repair retry -- without
writing anything. The job generates one block at a time and counts each in the Jobs panel, like
a generation job; a cancel stops it after the block in flight.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import GuidanceLevel, JobKind, TutorialBlockStatus
from app.errors import AdaptiveTrainerError
from app.jobs.queue import JobQueue
from app.jobs.runner import Progress, create_job, execute
from app.llm import StructuredLLMClient
from app.persistence.models import BackgroundJobRow, SubtopicRow, TopicRow, TutorialBlockRow
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever
from app.retrieval.embedder import Embedder
from app.subjects import profile_for_version
from app.tutorials.approval import subtopic_ids_of
from app.tutorials.generator import BlockRequest, generate_block, get_recipes


@dataclass(frozen=True)
class PlannedBlock:
    subtopic_id: int
    recipe_id: str
    guidance_level: GuidanceLevel


def plan_pregeneration(
    session: Session, curriculum_version_id: int, recipe_ids: list[str] | None = None
) -> tuple[list[PlannedBlock], int]:
    """The blocks still missing from the taxonomy's bank, and how many already exist."""
    subject = profile_for_version(session, curriculum_version_id).storage_key
    recipes = [r for r in get_recipes(subject) if recipe_ids is None or r.id in recipe_ids]
    subtopics = session.scalars(
        select(SubtopicRow.id)
        .join(TopicRow, TopicRow.id == SubtopicRow.topic_id)
        .where(TopicRow.curriculum_version_id == curriculum_version_id)
        .order_by(TopicRow.position, TopicRow.id, SubtopicRow.position, SubtopicRow.id)
    ).all()
    made = set(
        session.execute(
            select(
                TutorialBlockRow.subtopic_id,
                TutorialBlockRow.recipe_id,
                TutorialBlockRow.guidance_level,
            ).where(
                TutorialBlockRow.set_version_id.is_(None),
                TutorialBlockRow.status != TutorialBlockStatus.FAILED,
                TutorialBlockRow.subtopic_id.in_(subtopic_ids_of(curriculum_version_id)),
            )
        ).all()
    )
    planned: list[PlannedBlock] = []
    existing = 0
    for subtopic_id in subtopics:
        for recipe in recipes:
            for level in recipe.guidance_levels:
                if (subtopic_id, recipe.id, level) in made:
                    existing += 1
                else:
                    planned.append(PlannedBlock(subtopic_id, recipe.id, level))
    return planned, existing


def queue_pregeneration(
    session: Session,
    *,
    course: int | None,
    curriculum_version_id: int,
    planned: list[PlannedBlock],
    queue: JobQueue,
    client: StructuredLLMClient | None = None,
    embedder: Embedder | None = None,
) -> BackgroundJobRow:
    """Add the job and hand it to the queue. ``client``/``embedder`` are test seams."""
    count = len(planned)
    job = create_job(
        session,
        kind=JobKind.TUTORIAL_PREGENERATION,
        title=f"Tutorial blocks · {count} block{'s' if count != 1 else ''}",
        total=count,
        request={
            "curriculum_version_id": curriculum_version_id,
            "planned": [
                {
                    "subtopic_id": p.subtopic_id,
                    "recipe_id": p.recipe_id,
                    "guidance_level": p.guidance_level.value,
                }
                for p in planned
            ],
        },
        course_id=course,
    )
    session.commit()
    queue.submit(run_pregeneration, job.id, client=client, embedder=embedder)
    return job


def run_pregeneration(
    job_id: int,
    *,
    client: StructuredLLMClient | None = None,
    embedder: Embedder | None = None,
    session_factory=None,
) -> None:
    """Background body: generate each planned block, commit it, count it."""

    def body(session: Session, job: BackgroundJobRow, progress: Progress) -> dict:
        llm = client
        if llm is None:
            from app.web.routes.api.tutorials import get_tutorial_client

            llm = get_tutorial_client()
        if embedder is None:
            from app.web.routes.api.retrieval import get_query_embedder

            store = ChunkEmbeddingStore(session, get_query_embedder())
        else:
            store = ChunkEmbeddingStore(session, embedder)
        retriever = ChunkRetriever(session, store)
        made: list[int] = []
        failed: list[int] = []
        skipped: list[dict] = []
        for raw in job.request["planned"]:
            request = BlockRequest(
                subtopic_id=raw["subtopic_id"],
                recipe_id=raw["recipe_id"],
                guidance_level=GuidanceLevel(raw["guidance_level"]),
            )
            try:
                block = generate_block(session, request, client=llm, retriever=retriever)
            except AdaptiveTrainerError as exc:
                # E.g. no book text for the subtopic: nothing to write from, nothing spent.
                session.rollback()
                skipped.append({**raw, "reason": exc.message})
            else:
                (failed if block.status is TutorialBlockStatus.FAILED else made).append(block.id)
                session.commit()
            progress()
        return {"made": made, "failed": failed, "skipped": skipped}

    execute(job_id, body, session_factory=session_factory)
