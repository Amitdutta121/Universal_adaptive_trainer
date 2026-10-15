"""Chunk embeddings, chunk retrieval and the ``/chunks`` endpoints (Task 6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import book_documents as docs
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus
from app.persistence.models import (
    ChunkEmbeddingRow,
    ChunkRow,
    CourseRow,
    CurriculumVersionRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import ChunkRepository
from app.retrieval.chunks import (
    ChunkEmbeddingStore,
    ChunkRetriever,
    embedding_text,
    subtopic_query_text,
)
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


def _subtopic(
    session: Session, *, source_book_ids: list[int] | None = None, course_id: int | None = None
) -> SubtopicRow:
    version = CurriculumVersionRow(
        course_id=course_id,
        label="v1",
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
        source_book_ids=source_book_ids,
    )
    session.add(version)
    session.flush()
    topic = TopicRow(curriculum_version_id=version.id, name="Values and Variables", position=0)
    session.add(topic)
    session.flush()
    subtopic = SubtopicRow(
        topic_id=topic.id,
        name="Binding names to values",
        description="A variable is a name that refers to a value.",
        position=0,
    )
    session.add(subtopic)
    session.commit()
    return subtopic


def test_for_subtopic_searches_only_the_taxonomys_source_books(session: Session) -> None:
    in_scope = _book(session)
    out_of_scope = _book(session)
    subtopic = _subtopic(session, source_book_ids=[in_scope.id])
    retriever = ChunkRetriever(session, ChunkEmbeddingStore(session, KeywordEmbedder()))

    hits = retriever.for_subtopic(subtopic.id, top_k=10)

    assert hits
    assert {hit.book_id for hit in hits} == {in_scope.id}
    assert out_of_scope.id not in {hit.book_id for hit in hits}


def test_for_subtopic_without_source_books_stays_in_the_taxonomys_course(
    session: Session,
) -> None:
    mine, other = CourseRow(name="Mine"), CourseRow(name="Other")
    session.add_all([mine, other])
    session.flush()
    in_course = _book(session, course_id=mine.id)
    other_course = _book(session, course_id=other.id)
    subtopic = _subtopic(session, course_id=mine.id)
    retriever = ChunkRetriever(session, ChunkEmbeddingStore(session, KeywordEmbedder()))

    hits = retriever.for_subtopic(subtopic.id, top_k=10)

    assert hits
    assert {hit.book_id for hit in hits} == {in_course.id}
    assert other_course.id not in {hit.book_id for hit in hits}


def test_subtopic_query_text_shape(session: Session) -> None:
    subtopic = _subtopic(session)
    bare = SubtopicRow(topic_id=subtopic.topic_id, name="break", description=None)
    session.add(bare)
    session.flush()

    assert subtopic_query_text(subtopic) == (
        "Values and Variables - Binding names to values: "
        "A variable is a name that refers to a value."
    )
    assert subtopic_query_text(bare) == "Values and Variables - break"
