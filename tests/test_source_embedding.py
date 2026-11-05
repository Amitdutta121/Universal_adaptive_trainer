"""A source's chunks are embedded as soon as it is imported, not on the first round's search.

Also Task 137: two writers embedding the same chunks at once no longer fail.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import book_documents as docs
import pymupdf
import pytest
from book_uploads import finished_job
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.domain.enums import VideoAvailability
from app.ingestion.youtube import Segment
from app.persistence.models import BackgroundJobRow, ChunkEmbeddingRow, ChunkRow
from app.retrieval import source_embedding
from app.retrieval.chunks import ChunkEmbeddingStore
from app.web.routes.api.books import get_youtube_check, get_youtube_fetch


class FakeEmbedder:
    """Fixed-length vectors; ``before_embed`` runs inside each call, to act mid-embedding."""

    def __init__(self, model: str, before_embed: Callable[[], None] | None = None) -> None:
        self.model = model
        self.before_embed = before_embed
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.before_embed is not None:
            hook, self.before_embed = self.before_embed, None
            hook()
        return [[float(len(t)), 1.0, 0.5] for t in texts]


@pytest.fixture
def embedder(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    """Make the live embedder configured (tests otherwise run without an LLM key)."""
    fake = FakeEmbedder(settings.embedding_model)
    monkeypatch.setattr(source_embedding, "get_embedder", lambda _settings: fake)
    return fake


def _pdf(*pages: str) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _vectors(engine: Engine) -> tuple[int, int]:
    """(chunks with text, chunk vectors) across the database."""
    with Session(engine) as session:
        chunks = session.scalar(select(func.count()).select_from(ChunkRow))
        vectors = session.scalar(select(func.count()).select_from(ChunkEmbeddingRow))
        return chunks, vectors


def test_a_pdf_import_embeds_the_book_in_a_job_of_its_own(
    client: TestClient, engine: Engine, embedder: FakeEmbedder
) -> None:
    response = client.post(
        "/api/books",
        files={
            "file": ("textbook.pdf", _pdf("Chapter 1\n\nLoops repeat code."), "application/pdf")
        },
    )

    book = finished_job(client, response.json()["job_id"])["result"]["book"]
    jobs = client.get("/api/jobs").json()["jobs"]
    embedding = next(job for job in jobs if job["kind"] == "source_embedding")
    chunks, vectors = _vectors(engine)
    assert chunks > 0 and vectors == chunks
    assert embedding["status"] == "done"
    assert (embedding["done"], embedding["total"]) == (chunks, chunks)
    assert embedding["title"] == f"Embed · {book['title']}"
    assert embedding["link"] == f"/books/{book['id']}"
    assert embedding["counts"] == {"chunks": chunks}


def test_a_youtube_import_embeds_the_video(
    client: TestClient, configured_app: FastAPI, engine: Engine, embedder: FakeEmbedder
) -> None:
    segments = [Segment(float(i * 5), 5.0, f"Sentence number {i} about loops.") for i in range(6)]
    configured_app.dependency_overrides[get_youtube_fetch] = lambda: lambda _id: segments
    configured_app.dependency_overrides[get_youtube_check] = lambda: (
        lambda _id: (
            VideoAvailability.AVAILABLE,
            "Loops",
        )
    )

    first = client.post("/api/books/youtube", json={"url": "AbCdEfGhIjK"})
    again = client.post("/api/books/youtube", json={"url": "AbCdEfGhIjK"})

    assert first.status_code == 201 and again.status_code == 201
    chunks, vectors = _vectors(engine)
    assert chunks > 0 and vectors == chunks
    kinds = [job["kind"] for job in client.get("/api/jobs").json()["jobs"]]
    # The same video again has nothing left to embed, so it queues nothing.
    assert kinds.count("source_embedding") == 1


def test_without_an_embedder_an_import_queues_no_embedding(
    client: TestClient, session: Session
) -> None:
    response = client.post(
        "/api/books", files={"file": ("t.pdf", _pdf("Chapter 1\n\nHello."), "application/pdf")}
    )

    assert finished_job(client, response.json()["job_id"])["status"] == "done"
    kinds = session.scalars(select(BackgroundJobRow.kind)).all()
    assert [kind.value for kind in kinds] == ["book_import"]


def test_two_writers_embedding_the_same_chunks_both_succeed(
    settings: Settings, engine: Engine, session: Session
) -> None:
    """Task 137: the second writer's commit collides on (chunk, model); it keeps the first's."""
    book = docs.chunked_book(session, docs.think_python())
    session.commit()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    model = settings.embedding_model

    def other_writer() -> None:
        with factory() as other:
            ChunkEmbeddingStore(other, FakeEmbedder(model)).backfill([book.id])

    with factory() as mine:
        embedded = ChunkEmbeddingStore(mine, FakeEmbedder(model, other_writer)).backfill([book.id])

    chunks, vectors = _vectors(engine)
    assert embedded == chunks and vectors == chunks
