"""Model settings API: read, test, save, reset, model list (Task 42). Provider HTTP is mocked."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.backend import current_active_user
from app.config import Settings
from app.llm import probe as probe_module
from app.llm.probe import ProbeResult, probe
from app.persistence.models import ModelSettingRow, UserRow
from app.retrieval.reembed import run_embedding_switch
from app.web.routes.api import settings as settings_routes

NEW_KEY = "sk-or-new-key-abcdef123456"
BODY = {"model": "anthropic/claude-haiku-4.5", "api_key": NEW_KEY}


@pytest.fixture
def admin_client(configured_app: FastAPI, session: Session) -> Iterator[TestClient]:
    admin = UserRow(
        email="admin@example.com",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )
    session.add(admin)
    session.commit()
    configured_app.dependency_overrides[current_active_user] = lambda: admin
    with TestClient(configured_app) as test_client:
        yield test_client


@pytest.fixture
def probes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Settings, bool]]:
    """Every probe call; it passes, with dimension 1536 for embeddings."""
    calls: list[tuple[Settings, bool]] = []

    def fake(settings: Settings, *, embeddings: bool) -> ProbeResult:
        calls.append((settings, embeddings))
        return ProbeResult(ok=True, dimension=1536 if embeddings else None)

    monkeypatch.setattr(settings_routes, "probe", fake)
    return calls


def _rows(session: Session) -> list[ModelSettingRow]:
    session.expire_all()
    return list(session.scalars(select(ModelSettingRow)))


def test_anyone_signed_in_reads_env_settings_and_only_an_admin_edits(
    client: TestClient, session: Session, probes: list[Any]
) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["can_edit"] is False
    assert {r["role"] for r in body["roles"]} >= {"generation", "judges", "embeddings"}
    assert all(set(r["sources"].values()) == {"env"} for r in body["roles"])
    assert client.post("/api/settings/generation/test", json=BODY).status_code == 403
    put = client.put("/api/settings/generation", json={**BODY, "test_token": "x"})
    assert put.status_code == 403
    assert client.delete("/api/settings/generation").status_code == 403
    assert probes == [] and _rows(session) == []


def test_a_failed_test_returns_the_provider_error_and_saves_nothing(
    admin_client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        settings_routes,
        "probe",
        lambda settings, embeddings: ProbeResult(ok=False, error="HTTP 401: No auth credentials"),
    )

    response = admin_client.post("/api/settings/generation/test", json=BODY)

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "error": "HTTP 401: No auth credentials",
        "dimension": None,
        "test_token": None,
    }
    assert _rows(session) == []


def test_saving_needs_a_passing_test_of_the_same_config(
    admin_client: TestClient, session: Session, probes: list[Any]
) -> None:
    assert (
        admin_client.put("/api/settings/generation", json={**BODY, "test_token": ""}).status_code
        == 422
    )
    token = admin_client.post("/api/settings/generation/test", json=BODY).json()["test_token"]

    other_model = {**BODY, "model": "openai/gpt-4o-mini", "test_token": token}
    assert admin_client.put("/api/settings/generation", json=other_model).status_code == 422
    other_role = {**BODY, "test_token": token}
    assert admin_client.put("/api/settings/judges", json=other_role).status_code == 422
    assert _rows(session) == []

    saved = admin_client.put("/api/settings/generation", json={**BODY, "test_token": token})

    assert saved.status_code == 200
    role = saved.json()
    assert role["model"] == "anthropic/claude-haiku-4.5"
    assert role["sources"] == {"provider": "env", "model": "db", "base_url": "env", "api_key": "db"}
    assert role["api_key_masked"] == "••••3456"
    assert NEW_KEY not in saved.text
    [row] = _rows(session)
    assert row.api_key_encrypted and NEW_KEY.encode() not in row.api_key_encrypted
    assert probes[0][0].llm_api_key == SecretStr(NEW_KEY)


def test_a_saved_key_is_kept_when_the_next_edit_leaves_it_blank(
    admin_client: TestClient, session: Session, probes: list[Any]
) -> None:
    token = admin_client.post("/api/settings/generation/test", json=BODY).json()["test_token"]
    admin_client.put("/api/settings/generation", json={**BODY, "test_token": token})

    model_only = {"model": "openai/gpt-4o-mini"}
    token = admin_client.post("/api/settings/generation/test", json=model_only).json()["test_token"]
    saved = admin_client.put("/api/settings/generation", json={**model_only, "test_token": token})

    assert saved.json()["model"] == "openai/gpt-4o-mini"
    assert saved.json()["sources"]["api_key"] == "db"
    assert probes[1][0].llm_api_key == SecretStr(NEW_KEY)


def test_embeddings_test_reports_the_dimension_and_reset_returns_to_env(
    admin_client: TestClient,
    session: Session,
    probes: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A new embedding model is activated by a re-embedding job (Task 43); no chunks here.
    monkeypatch.setattr(
        settings_routes,
        "run_embedding_switch",
        lambda job_id: run_embedding_switch(job_id, embedder=SimpleNamespace(model="m")),
    )
    body = {"model": "openai/text-embedding-3-large", "api_key": NEW_KEY}
    tested = admin_client.post("/api/settings/embeddings/test", json=body).json()
    assert tested["ok"] and tested["dimension"] == 1536
    assert probes[0][1] is True and probes[0][0].embedding_model == "openai/text-embedding-3-large"
    admin_client.put("/api/settings/embeddings", json={**body, "test_token": tested["test_token"]})

    reset = admin_client.delete("/api/settings/embeddings")

    assert reset.status_code == 200
    assert reset.json()["switch"]["status"] == "queued"  # back to .env's model, via a switch
    roles = admin_client.get("/api/settings").json()["roles"]
    embeddings = next(r for r in roles if r["role"] == "embeddings")
    assert set(embeddings["sources"].values()) == {"env"}
    assert _rows(session) == []


def test_unknown_provider_and_untestable_role_are_refused(admin_client: TestClient) -> None:
    unknown = admin_client.post("/api/settings/generation/test", json={"provider": "acme"})
    assert unknown.status_code == 422
    transcription = admin_client.post("/api/settings/transcription/test", json=BODY)
    assert transcription.status_code == 422
    assert admin_client.post("/api/settings/nope/test", json=BODY).status_code == 422


def test_model_list_is_fetched_once_and_cached(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_routes._MODEL_CACHE.clear()
    calls: list[str] = []

    def fake_get(url: str, timeout: float) -> httpx.Response:
        calls.append(url)
        payload = {"data": [{"id": "z/model", "name": "Z"}, {"id": "a/model"}]}
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(settings_routes.httpx, "get", fake_get)

    first = client.get("/api/settings/models?provider=openrouter")
    second = client.get("/api/settings/models")

    assert first.json() == [{"id": "a/model", "name": "a/model"}, {"id": "z/model", "name": "Z"}]
    assert second.json() == first.json()
    assert calls == ["https://openrouter.ai/api/v1/models"]
    settings_routes._MODEL_CACHE.clear()


def test_probe_turns_provider_failures_into_a_message(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyed = settings.model_copy(update={"llm_api_key": SecretStr(NEW_KEY)})

    class Unreachable:
        def __init__(self, **_: object) -> None:
            error = openai.APIConnectionError(request=httpx.Request("POST", "https://x"))
            raise_ = SimpleNamespace(create=lambda **__: (_ for _ in ()).throw(error))
            self.chat = SimpleNamespace(completions=raise_)
            self.embeddings = raise_

    monkeypatch.setattr(probe_module.openai, "OpenAI", Unreachable)

    result = probe(keyed, embeddings=False)
    assert not result.ok and result.error and "Could not reach" in result.error
    assert NEW_KEY not in result.error
    assert probe(settings, embeddings=True).error == (
        "No API key: enter one, or set LLM_API_KEY in .env."
    )
