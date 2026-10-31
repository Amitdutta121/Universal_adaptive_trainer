"""Switching the embedding model without a moment of broken retrieval (Task 43).

Saving a new ``embeddings`` model does not change the active one. It stores the new
configuration as a pending row (``PENDING_EMBEDDINGS``) and queues a job that embeds every
current chunk in the new model. Retrieval keeps using the active row, and its vectors, the
whole time. Only when every chunk has a vector does one commit copy the pending row over the
active one, so a query sees either the old model with its vectors or the new one with its.

A failed or cancelled job never touches the active row; its pending row stays so the
Settings screen can say what happened, until the next switch replaces it. Vectors already
paid for are kept, so a retry only embeds the rest.

Vectors of the model being replaced are kept, so switching back costs nothing; the
vectors of any older model are deleted at the next successful switch.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import JobKind, RoundStatus
from app.errors import DomainRuleError
from app.jobs.cancel import raise_if_cancelled
from app.jobs.runner import Progress, create_job, execute
from app.persistence.models import BackgroundJobRow, ChunkEmbeddingRow, ModelSettingRow
from app.retrieval.chunks import ChunkEmbeddingStore
from app.retrieval.embedder import Embedder, build_embedder
from app.settings_store import (
    PENDING_EMBEDDINGS,
    ModelRole,
    apply_row,
    load_row,
    provider_configs,
    routed,
    settings_for,
)

_IN_FLIGHT = (RoundStatus.QUEUED, RoundStatus.RUNNING)


def switch_job(session: Session) -> BackgroundJobRow | None:
    """The job of the latest switch, whatever its state, or ``None`` if there is none."""
    pending = session.get(ModelSettingRow, PENDING_EMBEDDINGS)
    if pending is None or pending.job_id is None:
        return None
    return session.get(BackgroundJobRow, pending.job_id)


def start_switch(session: Session, pending: ModelSettingRow) -> BackgroundJobRow:
    """Store ``pending`` (an ``embeddings`` row not yet active) and queue its job.

    The caller commits and then submits :func:`run_embedding_switch` with the job id.
    """
    running = switch_job(session)
    if running is not None and RoundStatus(running.status) in _IN_FLIGHT:
        raise DomainRuleError(
            "An embedding model switch is already running.",
            detail="Wait for it to finish; its progress is on the Settings screen.",
        )
    embeddings = ModelRole.EMBEDDINGS
    base = routed(session, role=embeddings)
    model = apply_row(base, embeddings, pending, provider_configs(session)).embedding_model
    job = create_job(
        session,
        kind=JobKind.EMBEDDING_SWITCH,
        title=f"Re-embed every chunk with {model}",
        total=0,
        request={"model": model},
        course_id=None,
    )
    pending.role = PENDING_EMBEDDINGS
    pending.job_id = job.id
    session.merge(pending)
    return job


def run_embedding_switch(
    job_id: int,
    *,
    session_factory: Callable[[], Session] | None = None,
    embedder: Embedder | None = None,
) -> None:
    """Queue entry point. ``embedder`` is a test seam; production builds it from the row."""

    def body(session: Session, job: BackgroundJobRow, _progress: Progress) -> dict:
        return _switch(session, job, embedder)

    execute(job_id, body, session_factory=session_factory)


def _switch(session: Session, job: BackgroundJobRow, embedder: Embedder | None) -> dict:
    pending = session.get(ModelSettingRow, PENDING_EMBEDDINGS)
    if pending is None or pending.job_id != job.id:
        raise DomainRuleError("A newer embedding switch replaced this one.")
    base = get_settings()
    target = apply_row(
        routed(session, base, ModelRole.EMBEDDINGS),
        ModelRole.EMBEDDINGS,
        pending,
        provider_configs(session, base),
    )
    embedder = embedder or build_embedder(target)
    store = ChunkEmbeddingStore(session, embedder)
    job.total = len(store.missing())
    session.commit()

    def on_group(size: int) -> None:
        job.done += size
        session.commit()
        raise_if_cancelled(session, job)

    store.backfill(on_group=on_group)
    raise_if_cancelled(session, job)

    previous = settings_for(ModelRole.EMBEDDINGS, base, session=session).embedding_model
    active = load_row(session, ModelRole.EMBEDDINGS)
    if active is not None:
        session.delete(active)
        session.flush()
    if any((pending.provider, pending.model, pending.base_url, pending.api_key_encrypted)):
        session.add(
            ModelSettingRow(
                role=ModelRole.EMBEDDINGS.value,
                provider=pending.provider,
                model=pending.model,
                base_url=pending.base_url,
                api_key_encrypted=pending.api_key_encrypted,
                updated_by=pending.updated_by,
            )
        )
    session.delete(pending)
    keep = {embedder.model, previous}
    dropped = session.execute(
        delete(ChunkEmbeddingRow).where(ChunkEmbeddingRow.model.not_in(keep))
    ).rowcount
    session.commit()
    return {"model": embedder.model, "previous": previous, "dropped_vectors": dropped}
