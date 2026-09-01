"""Semantic retrieval over book sections: the embedding store and the retriever.

The provider is never called here. A ``KeywordEmbedder`` maps text to a
bag-of-words vector over a fixed vocabulary, so cosine ordering is deterministic
and a query about "variables" ranks the variable section first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import book_documents as docs
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import CurriculumStatus
from app.ingestion import BookImportService
from app.persistence.models import (
    CurriculumVersionRow,
    SectionEmbeddingRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import BookStructureRepository
from app.retrieval import SectionEmbeddingStore, SectionRetriever, subtopic_query_text
from app.retrieval.retriever import RetrievedSection
from app.web.routes.api.retrieval import get_query_embedder

VOCAB = [
    "program",
    "instructions",
    "interpreter",
    "python",
    "value",
    "variable",
    "name",
    "sequence",
]


class KeywordEmbedder:
    model = "keyword-test-v1"

    def __init__(self, vocab: Sequence[str] = VOCAB) -> None:
        self._vocab = list(vocab)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append([float(lowered.count(word)) for word in self._vocab])
        return vectors


@pytest.fixture
def book(session: Session, settings: Settings):
    row = BookImportService(session, settings).import_upload(
        filename="think_python.json", data=docs.to_bytes(docs.think_python())
    )
    session.commit()
    return row


@pytest.fixture
def embedder() -> KeywordEmbedder:
    return KeywordEmbedder()


def _section_id(session: Session, book_id: int, number: str) -> int:
    for row in BookStructureRepository(session).sections_in_book(book_id):
        if row.number == number:
            return row.id
    raise AssertionError(f"no section {number}")


class TestBackfill:
    def test_embeds_every_non_empty_section(self, session, book, embedder) -> None:
        store = SectionEmbeddingStore(session, embedder)
        result = store.backfill()
        session.commit()

        section_count = BookStructureRepository(session).section_count(book.id)
        assert result.total == section_count
        assert result.embedded == section_count
        assert result.skipped == 0
        assert session.query(SectionEmbeddingRow).count() == section_count

    def test_is_idempotent(self, session, book, embedder) -> None:
        store = SectionEmbeddingStore(session, embedder)
        store.backfill()
        session.commit()

        again = store.backfill()
        assert again.embedded == 0
        assert again.skipped == again.total

    def test_reembeds_only_changed_sections(self, session, book, embedder) -> None:
        store = SectionEmbeddingStore(session, embedder)
        store.backfill()
        session.commit()

        target = _section_id(session, book.id, "2.2")
        section = BookStructureRepository(session).get_section(target)
        section.text = section.text + " Extra words about variables."
        session.commit()

        result = store.backfill()
        assert result.embedded == 1
        assert result.skipped == result.total - 1

    def test_rebuild_reembeds_all(self, session, book, embedder) -> None:
        store = SectionEmbeddingStore(session, embedder)
        first = store.backfill()
        session.commit()
        rebuilt = store.backfill(rebuild=True)
        assert rebuilt.embedded == first.total

    def test_dry_run_writes_nothing(self, session, book, embedder) -> None:
        store = SectionEmbeddingStore(session, embedder)
        result = store.backfill(dry_run=True)
        assert result.embedded == result.total
        assert session.query(SectionEmbeddingRow).count() == 0


class TestLoad:
    def test_rows_are_l2_normalised(self, session, book, embedder) -> None:
        store = SectionEmbeddingStore(session, embedder)
        store.backfill()
        session.commit()

        loaded = store.load()
        assert len(loaded) == BookStructureRepository(session).section_count(book.id)
        norms = np.linalg.norm(loaded.matrix, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)

    def test_book_filter(self, session, settings, embedder) -> None:
        one = BookImportService(session, settings).import_upload(
            filename="a.json", data=docs.to_bytes(docs.think_python())
        )
        two = BookImportService(session, settings).import_upload(
            filename="b.json", data=docs.to_bytes(docs.think_python())
        )
        session.commit()
        store = SectionEmbeddingStore(session, embedder)
        store.backfill()
        session.commit()

        only_one = store.load(book_ids=[one.id])
        assert only_one.section_ids
        assert set(only_one.section_ids).isdisjoint(
            {s.id for s in BookStructureRepository(session).sections_in_book(two.id)}
        )
        assert store.load(book_ids=[]).section_ids == []


class TestSectionRetriever:
    def test_ranks_the_matching_section_first(self, session, book, embedder) -> None:
        store = SectionEmbeddingStore(session, embedder)
        store.backfill()
        session.commit()
        retriever = SectionRetriever(session, store)

        results = retriever.search("variable name value", top_k=3)
        assert results
        assert results[0].section_number == "2.2"  # "A variable is a name that refers to a value."
        assert results[0].score >= results[-1].score

    def test_empty_index_returns_empty(self, session, embedder) -> None:
        retriever = SectionRetriever(session, SectionEmbeddingStore(session, embedder))
        assert retriever.search("anything") == []

    def test_for_subtopic_uses_topic_name_and_scopes_to_source_books(
        self, session, settings, embedder
    ) -> None:
        in_scope = BookImportService(session, settings).import_upload(
            filename="in.json", data=docs.to_bytes(docs.think_python())
        )
        out_of_scope = BookImportService(session, settings).import_upload(
            filename="out.json", data=docs.to_bytes(docs.think_python())
        )
        session.commit()

        version = CurriculumVersionRow(
            label="v1",
            status=CurriculumStatus.APPROVED,
            approved_at=datetime.now(UTC),
            source_book_ids=[in_scope.id],
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

        store = SectionEmbeddingStore(session, embedder)
        store.backfill()
        session.commit()

        results = SectionRetriever(session, store).for_subtopic(subtopic.id, top_k=5)
        assert results
        out_ids = {s.id for s in BookStructureRepository(session).sections_in_book(out_of_scope.id)}
        assert all(r.section_id not in out_ids for r in results)

    def test_subtopic_query_text_shape(self, session) -> None:
        version = CurriculumVersionRow(label="v", status=CurriculumStatus.PROPOSED)
        session.add(version)
        session.flush()
        topic = TopicRow(curriculum_version_id=version.id, name="Loops", position=0)
        session.add(topic)
        session.flush()
        with_desc = SubtopicRow(topic_id=topic.id, name="range()", description="Using range().")
        without = SubtopicRow(topic_id=topic.id, name="break", description=None)
        session.add_all([with_desc, without])
        session.flush()

        assert subtopic_query_text(with_desc) == "Loops - range(): Using range()."
        assert subtopic_query_text(without) == "Loops - break"


class TestRetrievalEndpoint:
    @pytest.fixture
    def app(self, configured_app: FastAPI, embedder: KeywordEmbedder) -> FastAPI:
        configured_app.dependency_overrides[get_query_embedder] = lambda: embedder
        return configured_app

    @pytest.fixture
    def seeded(self, session: Session, settings: Settings, embedder: KeywordEmbedder):
        row = BookImportService(session, settings).import_upload(
            filename="think_python.json", data=docs.to_bytes(docs.think_python())
        )
        session.commit()
        store = SectionEmbeddingStore(session, embedder)
        store.backfill()
        session.commit()
        return row

    def test_query_returns_ranked_sections(self, app, seeded) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/retrieval/sections", params={"query": "variable name value"}
            )
        assert response.status_code == 200
        body = response.json()
        assert body
        assert body[0]["section_number"] == "2.2"
        assert {"section_id", "book_title", "score", "snippet"} <= body[0].keys()

    def test_requires_exactly_one_of_query_or_subtopic(self, app, seeded) -> None:
        with TestClient(app) as client:
            neither = client.get("/api/retrieval/sections")
            both = client.get("/api/retrieval/sections", params={"query": "x", "subtopic_id": 1})
        assert neither.status_code == 422
        assert both.status_code == 422

    def test_subtopic_id_path(self, app, session, settings, embedder) -> None:
        book = BookImportService(session, settings).import_upload(
            filename="tp.json", data=docs.to_bytes(docs.think_python())
        )
        session.commit()
        version = CurriculumVersionRow(
            label="v1",
            status=CurriculumStatus.APPROVED,
            approved_at=datetime.now(UTC),
            source_book_ids=[book.id],
        )
        session.add(version)
        session.flush()
        topic = TopicRow(curriculum_version_id=version.id, name="Values", position=0)
        session.add(topic)
        session.flush()
        subtopic = SubtopicRow(
            topic_id=topic.id,
            name="Variables",
            description="A variable is a name that refers to a value.",
        )
        session.add(subtopic)
        session.commit()
        SectionEmbeddingStore(session, embedder).backfill()
        session.commit()

        with TestClient(app) as client:
            response = client.get("/api/retrieval/sections", params={"subtopic_id": subtopic.id})
        assert response.status_code == 200
        assert response.json()[0]["section_number"] == "2.2"


def test_retrieved_section_is_frozen() -> None:
    result = RetrievedSection(1, 1, "B", None, "1.1", "T", 0.5, "snip")
    with pytest.raises(FrozenInstanceError):
        result.score = 0.9  # type: ignore[misc]
