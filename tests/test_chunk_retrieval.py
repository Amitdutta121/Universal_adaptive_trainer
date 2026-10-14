"""Chunk embeddings, chunk retrieval and the ``/chunks`` endpoints (Task 6)."""

from __future__ import annotations

from collections.abc import Sequence

import book_documents as docs
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.persistence.models import ChunkEmbeddingRow, ChunkRow
from app.persistence.repositories import ChunkRepository
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever, embedding_text
from app.web.routes.api.retrieval import get_query_embedder


class KeywordEmbedder:
    """Bag-of-words over a fixed vocabulary; counts every call's texts."""

    VOCAB = ("program", "python", "value", "variable", "interpreter")

    def __init__(self, model: str = "keyword-v1") -> None:
        self.model = model
        self.embedded: list[str] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[float(t.lower().count(word)) for word in self.VOCAB] for t in texts]


def _book(session: Session, course_id: int | None = None):
    book = docs.chunked_book(session, docs.think_python(), course_id=course_id)
    session.commit()
    return book


def test_a_chunk_is_embedded_with_its_heading_path(session: Session) -> None:
    book = _book(session)
    chunk = ChunkRepository(session).list_for_book(book.id)[0]
    assert embedding_text(chunk) == (
        "1 The Way of the Program \u203a 1.1 What Is a Program?\n\n"
        "A program is a sequence of instructions."
    )


def test_the_same_model_reuses_the_cache_and_a_new_model_re_embeds(session: Session) -> None:
    _book(session)
    first = KeywordEmbedder("model-a")
    store = ChunkEmbeddingStore(session, first)

    assert store.backfill() == 4
    assert store.backfill() == 0
    assert len(first.embedded) == 4

    assert ChunkEmbeddingStore(session, KeywordEmbedder("model-b")).backfill() == 4
    assert session.query(ChunkEmbeddingRow).count() == 8
    assert ChunkEmbeddingStore(session, KeywordEmbedder("model-a")).backfill() == 0


def test_search_ranks_by_similarity_and_embeds_what_is_missing(session: Session) -> None:
    _book(session)
    embedder = KeywordEmbedder()
    retriever = ChunkRetriever(session, ChunkEmbeddingStore(session, embedder))

    hits = retriever.search("a variable holds a value", top_k=2)

    assert [hit.heading_path[-1] for hit in hits] == ["2.2 Variables", "2.1 Values and Types"]
    assert hits[0].page_start == 33
    assert hits[0].score >= hits[1].score


def test_only_the_current_version_is_searched(session: Session) -> None:
    book = _book(session)
    ChunkRepository(session).add_version(
        book, [ChunkRow(text="Python interpreter only.", page_start=1, page_end=1)]
    )
    session.commit()
    retriever = ChunkRetriever(session, ChunkEmbeddingStore(session, KeywordEmbedder()))

    hits = retriever.search("variable value program interpreter", top_k=10)

    assert [hit.snippet for hit in hits] == ["Python interpreter only."]


def test_list_by_page_and_get_one(client: TestClient, session: Session) -> None:
    book = _book(session)

    listed = client.get("/api/chunks", params={"book_id": book.id}).json()
    assert listed["total"] == 4
    on_page = client.get("/api/chunks", params={"book_id": book.id, "page": 18}).json()
    assert [chunk["heading_path"][-1] for chunk in on_page["chunks"]] == [
        "1.1 What Is a Program?",
        "1.2 Running Python",
    ]

    chunk_id = on_page["chunks"][0]["id"]
    one = client.get(f"/api/chunks/{chunk_id}").json()
    assert one["citation"] == (
        "Think Python, 1 The Way of the Program \u203a 1.1 What Is a Program? (Pages 17\u201318)"
    )
    assert one["text"] == "A program is a sequence of instructions."
    assert client.get("/api/chunks/missing").status_code == 404


def test_search_endpoint(client: TestClient, session: Session) -> None:
    _book(session)
    client.app.dependency_overrides[get_query_embedder] = KeywordEmbedder
    try:
        response = client.get("/api/chunks/search", params={"q": "variable", "top_k": 1})
        neither = client.get("/api/chunks/search")
    finally:
        client.app.dependency_overrides.pop(get_query_embedder)

    assert response.status_code == 200, response.text
    assert response.json()[0]["heading_path"][-1] == "2.2 Variables"
    assert neither.status_code in (400, 422)
