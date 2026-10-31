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
from app.config import Settings, get_settings
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


def test_any_signed_in_account_edits_by_default(
    client: TestClient, session: Session, probes: list[Any]
) -> None:
    assert client.get("/api/settings").json()["can_edit"] is True
    token = client.post("/api/settings/generation/test", json=BODY).json()["test_token"]
    saved = client.put("/api/settings/generation", json={**BODY, "test_token": token})

    assert saved.status_code == 200
    assert [row.model for row in _rows(session)] == [BODY["model"]]
    assert client.delete("/api/settings/generation").status_code == 200


def test_anyone_signed_in_reads_env_settings_and_only_an_admin_edits(
    client: TestClient, session: Session, probes: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_SETTINGS_ADMIN_ONLY", "true")
    get_settings.cache_clear()
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
        payload = {
            "data": [
                {
                    "id": "z/model",
                    "name": "Z",
                    "context_length": 128000,
                    "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                },
                {"id": "a/model", "pricing": {"prompt": "n/a"}},
            ]
        }
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(settings_routes.httpx, "get", fake_get)

    first = client.get("/api/settings/models?provider=openrouter")
    second = client.get("/api/settings/models")

    # Prices become USD per million tokens; anything missing or malformed is left out.
    unknown = {"context_length": None, "prompt_price": None, "completion_price": None}
    assert first.json() == [
        {"id": "a/model", "name": "a/model", **unknown},
        {
            "id": "z/model",
            "name": "Z",
            "context_length": 128000,
            "prompt_price": 2.5,
            "completion_price": 10.0,
        },
    ]
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



@pytest.mark.parametrize(
    ("model", "limit"),
    [("gpt-5-mini", "max_completion_tokens"), ("deepseek/deepseek-chat", "max_tokens")],
)
def test_probe_uses_the_token_limit_the_model_accepts(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, model: str, limit: str
) -> None:
    """Azure's gpt-5-mini answers HTTP 400 to ``max_tokens``; the probe must not send it."""
    sent: dict[str, object] = {}

    class Recording:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=sent.update))

    monkeypatch.setattr(probe_module.openai, "OpenAI", Recording)
    keyed = settings.model_copy(update={"llm_api_key": SecretStr(NEW_KEY), "llm_model": model})

    assert probe(keyed, embeddings=False).ok
    assert sent[limit] == 16
    assert ({"max_tokens", "max_completion_tokens"} - {limit}).isdisjoint(sent)


AZURE_URL = "https://lab.services.ai.azure.com/openai/v1/"


def _on_azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_API_KEY", "sk-or-env-key-123456")
    monkeypatch.setenv("AZURE_BASE_URL", AZURE_URL)
    monkeypatch.setenv("AZURE_API_KEY", "azure-key-abcdef123456")
    get_settings.cache_clear()


def test_the_route_toggle_points_every_unsaved_role_at_azure_and_back(
    admin_client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.settings_store import ModelRole, settings_for

    _on_azure_env(monkeypatch)
    before = admin_client.get("/api/settings").json()
    azure = next(p for p in before["providers"] if p["id"] == "azure")
    assert (before["route"], before["route_source"], azure["configured"]) == (
        "openrouter",
        "env",
        True,
    )

    after = admin_client.put("/api/settings/route", json={"route": "azure"}).json()

    assert (after["route"], after["route_source"]) == ("azure", "db")
    roles = {r["role"]: r for r in after["roles"]}
    assert roles["generation"]["base_url"] == AZURE_URL
    assert roles["generation"]["model"] == "gpt-5-mini"
    assert roles["embeddings"]["model"] == "text-embedding-3-small"
    assert roles["generation"]["api_key_masked"] == "••••3456"
    assert settings_for(ModelRole.JUDGES).llm_base_url == AZURE_URL
    assert admin_client.get("/api/health").json()["llm_status"] == "azure/gpt-5-mini"

    back = admin_client.put("/api/settings/route", json={"route": "openrouter"}).json()
    assert back["route"] == "openrouter"
    assert settings_for(ModelRole.JUDGES).llm_base_url is None


def test_a_role_saved_on_its_own_keeps_its_settings_on_azure(
    admin_client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.settings_store import ModelRole, settings_for

    _on_azure_env(monkeypatch)
    session.add(ModelSettingRow(role="judges", model="anthropic/claude-haiku-4.5"))
    session.commit()

    admin_client.put("/api/settings/route", json={"route": "azure"})

    judges = settings_for(ModelRole.JUDGES)
    assert judges.llm_model == "anthropic/claude-haiku-4.5"
    assert judges.llm_base_url == AZURE_URL  # only the fields the row sets are its own


def test_azure_is_refused_until_configured(admin_client: TestClient) -> None:
    refused = admin_client.put("/api/settings/route", json={"route": "azure"})
    assert refused.status_code == 422
    providers = admin_client.get("/api/settings").json()["providers"]
    assert next(p for p in providers if p["id"] == "azure")["configured"] is False


def test_only_an_admin_toggles_the_route_when_admin_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.put("/api/settings/route", json={"route": "openrouter"}).status_code == 200
    monkeypatch.setenv("MODEL_SETTINGS_ADMIN_ONLY", "true")
    get_settings.cache_clear()
    assert client.put("/api/settings/route", json={"route": "openrouter"}).status_code == 403


# -- Providers (ADR-068) ----------------------------------------------------------------------

ANTHROPIC_KEY = "sk-ant-test-key-987654"


def test_saving_a_provider_tests_it_first_and_stores_the_key_encrypted(
    admin_client: TestClient, session: Session, probes: list[Any]
) -> None:
    saved = admin_client.put(
        "/api/settings/providers/anthropic", json={"api_key": ANTHROPIC_KEY}
    )

    assert saved.status_code == 200
    tested, embeddings = probes[-1]
    assert not embeddings
    assert tested.llm_base_url == "https://api.anthropic.com/v1/"
    assert tested.llm_model == "claude-haiku-4-5"
    assert tested.llm_api_key is not None
    assert tested.llm_api_key.get_secret_value() == ANTHROPIC_KEY
    anthropic = next(p for p in saved.json()["providers"] if p["id"] == "anthropic")
    assert anthropic["configured"] is True
    assert anthropic["api_key_masked"] == "••••7654"
    assert anthropic["saved"] == ["api_key"]
    row = next(r for r in _rows(session) if r.role == "provider.anthropic")
    assert row.api_key_encrypted and ANTHROPIC_KEY.encode() not in row.api_key_encrypted


def test_a_provider_that_fails_its_test_call_is_not_saved(
    admin_client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        settings_routes,
        "probe",
        lambda settings, *, embeddings: ProbeResult(ok=False, error="HTTP 401: bad key"),
    )

    refused = admin_client.put("/api/settings/providers/xai", json={"api_key": "xai-bad-key-1"})

    assert refused.status_code == 422
    assert "HTTP 401: bad key" in refused.text
    assert not [r for r in _rows(session) if r.role == "provider.xai"]


def test_the_default_provider_moves_every_role_but_embeddings_stay_where_they_can_embed(
    admin_client: TestClient, probes: list[Any]
) -> None:
    from app.settings_store import ModelRole, settings_for

    assert admin_client.put("/api/settings/route", json={"route": "anthropic"}).status_code == 422
    admin_client.put("/api/settings/providers/anthropic", json={"api_key": ANTHROPIC_KEY})

    after = admin_client.put("/api/settings/route", json={"route": "anthropic"}).json()

    roles = {r["role"]: r for r in after["roles"]}
    assert (roles["generation"]["provider"], roles["generation"]["model"]) == (
        "anthropic",
        "claude-haiku-4-5",
    )
    assert roles["judges"]["provider"] == "anthropic"
    # Claude has no embedding models, so retrieval keeps OpenRouter's.
    assert roles["embeddings"]["provider"] == "openrouter"
    judges = settings_for(ModelRole.JUDGES)
    assert judges.llm_base_url == "https://api.anthropic.com/v1/"
    assert judges.llm_api_key is not None
    assert judges.llm_api_key.get_secret_value() == ANTHROPIC_KEY


def test_a_role_can_use_its_own_provider_with_that_providers_key(
    admin_client: TestClient, probes: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.settings_store import ModelRole, settings_for

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-env-4321")
    get_settings.cache_clear()
    body = {"provider": "deepseek", "model": "deepseek-reasoner", "clear_api_key": True}
    token = admin_client.post("/api/settings/judges/test", json=body).json()["test_token"]

    saved = admin_client.put("/api/settings/judges", json={**body, "test_token": token})

    assert (saved.json()["provider"], saved.json()["model"]) == ("deepseek", "deepseek-reasoner")
    judges = settings_for(ModelRole.JUDGES)
    assert judges.llm_base_url == "https://api.deepseek.com/v1"
    assert judges.llm_api_key is not None
    assert judges.llm_api_key.get_secret_value() == "sk-deepseek-env-4321"
    assert settings_for(ModelRole.GENERATION).llm_base_url is None  # still OpenRouter


def test_embeddings_refuse_a_provider_without_embedding_models(
    admin_client: TestClient, probes: list[Any]
) -> None:
    refused = admin_client.post("/api/settings/embeddings/test", json={"provider": "anthropic"})
    assert refused.status_code == 422


def test_each_provider_lists_its_models_with_its_own_auth(
    admin_client: TestClient, probes: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_routes._MODEL_CACHE.clear()
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, timeout: float, headers=None, params=None) -> httpx.Response:
        calls.append((url, headers or {}))
        if "anthropic" in url:
            payload = {"data": [{"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5"}]}
        else:
            payload = {"data": [{"id": "deepseek-chat"}]}
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(settings_routes.httpx, "get", fake_get)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-env-4321")
    get_settings.cache_clear()
    admin_client.put("/api/settings/providers/anthropic", json={"api_key": ANTHROPIC_KEY})

    claude = admin_client.get("/api/settings/models?provider=anthropic").json()
    deepseek = admin_client.get("/api/settings/models?provider=deepseek").json()

    assert claude[0]["name"] == "Claude Haiku 4.5"
    assert deepseek[0]["id"] == "deepseek-chat"
    assert calls[0] == (
        "https://api.anthropic.com/v1/models",
        {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
    )
    assert calls[1] == (
        "https://api.deepseek.com/v1/models",
        {"Authorization": "Bearer sk-deepseek-env-4321"},
    )
    assert admin_client.get("/api/settings/models?provider=azure").json() == []
    settings_routes._MODEL_CACHE.clear()


def test_claude_is_asked_for_fenced_json(
    configured_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import instructor

    from app.llm.client import get_structured_client

    monkeypatch.setenv("LLM_ROUTE", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", ANTHROPIC_KEY)
    get_settings.cache_clear()

    client = get_structured_client()

    assert client.description == "anthropic/claude-haiku-4-5"
    assert client._client.mode is instructor.Mode.MD_JSON  # type: ignore[attr-defined]
