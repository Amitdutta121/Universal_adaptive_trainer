"""Switching the embedding model re-embeds first and swaps atomically (Task 43)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import book_documents as docs
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.backend import current_active_user
from app.config import Settings
from app.domain.enums import RoundStatus
from app.errors import DomainRuleError, LLMRequestError
from app.llm.probe import ProbeResult
from app.persistence.models import BackgroundJobRow, ChunkEmbeddingRow, ModelSettingRow, UserRow
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever
from app.retrieval.reembed import run_embedding_switch, start_switch
from app.settings_store import PENDING_EMBEDDINGS, ModelRole, settings_for
from app.web.routes.api import settings as settings_routes

VOCAB = ("program", "python", "value", "variable", "interpreter")


class FakeEmbedder:
    """Bag of words; ``before_embed`` runs before each call, to act mid-job."""

    def __init__(self, model: str, before_embed: Callable[[], None] | None = None) -> None:
        self.model = model
        self.before_embed = before_embed
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.before_embed is not None:
            self.before_embed()
        return [[float(t.lower().count(w)) + 0.01 for w in VOCAB] for t in texts]


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def book(settings: Settings, session: Session) -> int:
    """A chunked book whose chunks are embedded in the active (``.env``) model."""
    row = docs.chunked_book(session, docs.think_python())
    session.commit()
    ChunkEmbeddingStore(session, FakeEmbedder(settings.embedding_model)).backfill()
    return row.id


def _vectors(session: Session, model: str) -> int:
    return session.scalar(
        select(func.count()).select_from(ChunkEmbeddingRow).where(ChunkEmbeddingRow.model == model)
    )


def _search_active(factory: sessionmaker[Session]) -> list[str]:
    """What retrieval returns right now, in whatever model is active."""
    with factory() as s:
        model = settings_for(ModelRole.EMBEDDINGS, session=s).embedding_model
        retriever = ChunkRetriever(s, ChunkEmbeddingStore(s, FakeEmbedder(model)), hybrid=False)
        before = _vectors(s, model)
        hits = retriever.search("python program", top_k=3)
        assert _vectors(s, model) == before, "the active model had to embed on the fly"
        return [h.chunk_id for h in hits]


def _start(session: Session, model: str) -> int:
    job = start_switch(session, ModelSettingRow(role=ModelRole.EMBEDDINGS.value, model=model))
    session.commit()
    return job.id


def test_retrieval_stays_on_the_old_model_until_the_switch_completes(
    settings: Settings, session: Session, factory: sessionmaker[Session], book: int
) -> None:
    old = settings.embedding_model
    before = _search_active(factory)
    mid_job: list[tuple[str, list[str]]] = []

    def during() -> None:
        with factory() as s:
            model = settings_for(ModelRole.EMBEDDINGS, session=s).embedding_model
        mid_job.append((model, _search_active(factory)))

    job_id = _start(session, "new-v2")
    run_embedding_switch(job_id, session_factory=factory, embedder=FakeEmbedder("new-v2", during))

    assert mid_job and all(model == old and hits == before for model, hits in mid_job)
    session.expire_all()
    job = session.get(BackgroundJobRow, job_id)
    assert RoundStatus(job.status) is RoundStatus.DONE
    assert job.done == job.total == _vectors(session, old) > 0
    assert settings_for(ModelRole.EMBEDDINGS, session=session).embedding_model == "new-v2"
    assert session.get(ModelSettingRow, PENDING_EMBEDDINGS) is None
    assert _search_active(factory)  # the new model already has every vector
    assert _vectors(session, old) == _vectors(session, "new-v2")  # old vectors kept


def test_the_next_successful_switch_drops_the_vectors_two_models_back(
    settings: Settings, session: Session, factory: sessionmaker[Session], book: int
) -> None:
    old = settings.embedding_model
    run_embedding_switch(
        _start(session, "new-v2"), session_factory=factory, embedder=FakeEmbedder("new-v2")
    )
    run_embedding_switch(
        _start(session, "third-v3"), session_factory=factory, embedder=FakeEmbedder("third-v3")
    )

    session.expire_all()
    assert _vectors(session, old) == 0
    assert _vectors(session, "new-v2") > 0  # the model just replaced
    assert _vectors(session, "third-v3") > 0


@pytest.mark.parametrize("how", ["fails", "cancelled"])
def test_a_failed_or_cancelled_switch_leaves_the_old_model_active(
    how: str, settings: Settings, session: Session, factory: sessionmaker[Session], book: int
) -> None:
    old = settings.embedding_model
    before = _search_active(factory)
    job_id = _start(session, "new-v2")

    def interrupt() -> None:
        if how == "fails":
            raise LLMRequestError("The embedding provider could not be reached.")
        with factory() as s:
            s.get(BackgroundJobRow, job_id).cancel_requested_at = datetime.now(UTC)
            s.commit()

    run_embedding_switch(
        job_id, session_factory=factory, embedder=FakeEmbedder("new-v2", interrupt)
    )

    session.expire_all()
    job = session.get(BackgroundJobRow, job_id)
    assert RoundStatus(job.status) is RoundStatus.FAILED
    assert (job.cancel_requested_at is not None) == (how == "cancelled")
    assert settings_for(ModelRole.EMBEDDINGS, session=session).embedding_model == old
    assert _search_active(factory) == before
    assert session.get(ModelSettingRow, PENDING_EMBEDDINGS).job_id == job_id  # shown in Settings


def test_a_second_switch_is_refused_while_one_is_in_flight(session: Session, book: int) -> None:
    _start(session, "new-v2")

    with pytest.raises(DomainRuleError, match="already running"):
        _start(session, "third-v3")


@pytest.fixture
def admin_client(
    configured_app: FastAPI, session: Session, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    admin = UserRow(email="a@example.com", hashed_password="x", is_superuser=True, is_verified=True)
    session.add(admin)
    session.commit()
    configured_app.dependency_overrides[current_active_user] = lambda: admin
    monkeypatch.setattr(
        settings_routes,
        "probe",
        lambda settings, embeddings: ProbeResult(ok=True, dimension=5),
    )
    return TestClient(configured_app)


def test_saving_a_new_embedding_model_runs_the_switch_job(
    settings: Settings,
    session: Session,
    book: int,
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: list[int] = []

    def fake_run(job_id: int) -> None:
        ran.append(job_id)
        run_embedding_switch(job_id, embedder=FakeEmbedder("new-v2"))

    monkeypatch.setattr(settings_routes, "run_embedding_switch", fake_run)
    body = {"model": "new-v2", "api_key": "sk-or-some-key-123456"}
    token = admin_client.post("/api/settings/embeddings/test", json=body).json()["test_token"]

    saved = admin_client.put("/api/settings/embeddings", json={**body, "test_token": token})

    assert saved.status_code == 200
    # The response is built before the background job runs: still the old model.
    assert saved.json()["model"] == settings.embedding_model
    assert saved.json()["switch"]["status"] == "queued"
    assert len(ran) == 1
    after = admin_client.get("/api/settings").json()["roles"]
    embeddings = next(r for r in after if r["role"] == "embeddings")
    assert embeddings["model"] == "new-v2"
    assert embeddings["sources"]["api_key"] == "db"
    assert embeddings["switch"] is None  # the pending row is gone once it is active
    jobs = admin_client.get("/api/jobs").json()["jobs"]
    assert jobs[0]["kind"] == "embedding_switch" and jobs[0]["status"] == "done"


def test_saving_the_same_embedding_model_saves_without_a_job(
    settings: Settings, session: Session, book: int, admin_client: TestClient
) -> None:
    body = {"api_key": "sk-or-some-key-123456"}
    token = admin_client.post("/api/settings/embeddings/test", json=body).json()["test_token"]

    saved = admin_client.put("/api/settings/embeddings", json={**body, "test_token": token})

    assert saved.json()["sources"]["api_key"] == "db"
    assert saved.json()["switch"] is None
    assert session.scalar(select(func.count()).select_from(BackgroundJobRow)) == 0
