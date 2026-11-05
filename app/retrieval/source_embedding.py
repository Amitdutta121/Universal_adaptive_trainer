"""Embed a source's chunks as soon as it is imported.

Retrieval embeds whatever is missing on first search (``ChunkRetriever.search``), so without
this the first question round on a new course spends minutes embedding every book and video
before it generates anything. Importing a book, a new book version or a YouTube video queues
this job instead; it shows in the Jobs panel, and a round that starts while it runs embeds
nothing twice (``ChunkEmbeddingStore.backfill`` tolerates a concurrent writer).

No job is made when no embedder is configured or every chunk already has a vector.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import JobKind
from app.errors import ConfigurationError
from app.jobs.cancel import raise_if_cancelled
from app.jobs.runner import Progress, create_job, execute
from app.persistence.models import BackgroundJobRow, BookRow
from app.retrieval.chunks import ChunkEmbeddingStore
from app.retrieval.embedder import Embedder, get_embedder

logger = logging.getLogger(__name__)


def _live_embedder() -> Embedder | None:
    try:
        return get_embedder(get_settings())
    except ConfigurationError:
        return None


def start_source_embedding(
    session: Session, book_id: int, *, embedder: Embedder | None = None
) -> BackgroundJobRow | None:
    """Add a queued job embedding ``book_id``'s missing chunks, or ``None`` if none are.

    The caller commits, then submits :func:`run_source_embedding` with the job id.
    """
    embedder = embedder or _live_embedder()
    if embedder is None:
        return None
    missing = len(ChunkEmbeddingStore(session, embedder).missing([book_id]))
    if not missing:
        return None
    book = session.get(BookRow, book_id)
    assert book is not None
    return create_job(
        session,
        kind=JobKind.SOURCE_EMBEDDING,
        title=f"Embed · {book.title}",
        total=missing,
        request={"book_id": book_id},
        course_id=book.course_id,
    )


def run_source_embedding(
    job_id: int,
    *,
    session_factory: Callable[[], Session] | None = None,
    embedder: Embedder | None = None,
) -> None:
    """Queue entry point. ``embedder`` is a test seam; production uses the live one."""

    def body(session: Session, job: BackgroundJobRow, _progress: Progress) -> dict:
        live = embedder or get_embedder(get_settings())
        store = ChunkEmbeddingStore(session, live)
        book_ids = [int(job.request["book_id"])]
        job.total = len(store.missing(book_ids))
        session.commit()

        def on_group(size: int) -> None:
            job.done += size
            session.commit()
            raise_if_cancelled(session, job)

        embedded = store.backfill(book_ids, on_group=on_group)
        return {"book_id": book_ids[0], "embedded": embedded}

    execute(job_id, body, session_factory=session_factory)


def embed_after_import(
    import_job_id: int,
    *,
    session_factory: Callable[[], Session] | None = None,
    embedder: Embedder | None = None,
) -> None:
    """After a book import job: embed the imported book. Never raises (a background task)."""
    if session_factory is None:
        from app.persistence.database import get_session_factory

        session_factory = get_session_factory()
    session = session_factory()
    try:
        imported = session.get(BackgroundJobRow, import_job_id)
        book = ((imported.result or {}).get("book") or {}) if imported else {}
        if not book.get("id"):
            return
        job = start_source_embedding(session, int(book["id"]), embedder=embedder)
        if job is None:
            return
        session.commit()
        job_id = job.id
    except Exception:
        logger.exception("could not queue embedding after import job %s", import_job_id)
        session.rollback()
        return
    finally:
        session.close()
    run_source_embedding(job_id, session_factory=session_factory, embedder=embedder)
