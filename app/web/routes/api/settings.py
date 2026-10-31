"""Model settings per role: read, test, save, reset, and the provider's model list (Task 42).

Providers (ADR-068): each one's URL, key and default model can be saved here over ``.env``,
and one of them is the default every role follows unless it names its own.

Any signed-in professor can read the settings (keys masked), and by default test, save and
reset them too (ADR-067). With ``MODEL_SETTINGS_ADMIN_ONLY`` on, those three need an admin (a
superuser), since they change what the whole instance spends money on.
Saving needs the token from a passing Test of exactly the configuration being saved.
"""

from __future__ import annotations

import hashlib
import time
from typing import Annotated

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Query
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.config import LLMProvider, Settings, get_settings
from app.domain.enums import RoundStatus
from app.errors import AdminRequiredError, DomainRuleError, LLMRequestError
from app.jobs.queue import JobQueue, JobQueueDep
from app.llm.probe import probe
from app.llm_providers import OPENROUTER_BASE_URL, provider_spec
from app.persistence.models import ModelSettingRow, UserRow
from app.retrieval.reembed import run_embedding_switch, start_switch, switch_job
from app.settings_store import (
    PROVIDER_PREFIX,
    ModelRole,
    ProviderConfig,
    apply_row,
    candidate,
    check_test_token,
    clear_provider,
    decrypt_api_key,
    issue_test_token,
    load_route,
    load_row,
    mask_key,
    on_provider,
    provider_config,
    provider_configs,
    routed,
    save_provider,
    save_route,
    settings_for,
)
from app.web.routes.api.deps import CurrentUser, DbSession
from app.web.routes.api.schemas import (
    EmbeddingSwitchOut,
    ModelSettingsResponse,
    ProviderModel,
    ProviderOut,
    ProviderUpdate,
    RoleSettingsResponse,
    RoleSettingsSave,
    RoleSettingsUpdate,
    RouteUpdate,
    SettingsTestResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])

_IN_FLIGHT = (RoundStatus.QUEUED, RoundStatus.RUNNING)
#: Roles whose Test has nothing to call yet; they can't be saved until it does.
_UNTESTABLE = {ModelRole.TRANSCRIPTION}
#: Provider model lists, refreshed hourly, keyed by provider (and endpoint+key fingerprint).
_MODEL_CACHE: dict[str, tuple[float, list[ProviderModel]]] = {}
#: Anthropic's model list is its own API, not the OpenAI-compatible one.
_ANTHROPIC_VERSION = "2023-06-01"
_MODEL_CACHE_SECONDS = 3600


def can_edit(user: UserRow) -> bool:
    return user.is_superuser or not get_settings().model_settings_admin_only


def require_admin(user: CurrentUser) -> UserRow:
    if not can_edit(user):
        raise AdminRequiredError(
            "Only an admin can change model settings.",
            detail="Ask an admin, or create one with `python -m app.auth.create_user --superuser`.",
        )
    return user


AdminUser = Annotated[UserRow, Depends(require_admin)]


def _key_in_effect(row: ModelSettingRow | None, base: Settings) -> bool:
    """A saved key that no longer decrypts is not in effect: the .env key is."""
    if row is None or not row.api_key_encrypted:
        return False
    try:
        decrypt_api_key(row.api_key_encrypted, base)
    except InvalidToken:
        return False
    return True


def _switch_out(session: Session) -> EmbeddingSwitchOut | None:
    job = switch_job(session)
    if job is None:
        return None
    status = RoundStatus(job.status).value
    if status == "failed" and job.cancel_requested_at is not None:
        status = "cancelled"
    return EmbeddingSwitchOut(
        job_id=f"job-{job.id}",
        model=(job.request or {}).get("model", ""),
        status=status,
        done=job.done,
        total=job.total,
        error=job.error,
    )


def _describe(session: Session, role: ModelRole) -> RoleSettingsResponse:
    base = routed(session, role=role)
    row = load_row(session, role)
    effective = apply_row(base, role, row, provider_configs(session))
    from_db = {
        "provider": bool(row and row.provider),
        "model": bool(row and row.model),
        "base_url": bool(row and row.base_url),
        "api_key": _key_in_effect(row, base),
    }
    return RoleSettingsResponse(
        role=role.value,
        provider=effective.llm_provider.value,
        model=effective.embedding_model if role is ModelRole.EMBEDDINGS else effective.llm_model,
        base_url=effective.llm_base_url,
        api_key_masked=mask_key(effective.llm_api_key),
        sources={field: "db" if db else "env" for field, db in from_db.items()},
        configured=effective.llm_configured,
        testable=role not in _UNTESTABLE,
        switch=_switch_out(session) if role is ModelRole.EMBEDDINGS else None,
    )


def _save_or_switch(
    session: Session, role: ModelRole, row: ModelSettingRow, queue: JobQueue
) -> None:
    """Save ``row`` now, or, for an embeddings row naming a new model, start a switch."""
    if role is ModelRole.EMBEDDINGS:
        running = switch_job(session)
        if running is not None and RoundStatus(running.status) in _IN_FLIGHT:
            raise DomainRuleError(
                "An embedding model switch is running.",
                detail="Wait for it to finish; its progress is on the Settings screen.",
            )
        base = routed(session, role=role)
        new_model = apply_row(base, role, row, provider_configs(session)).embedding_model
        if new_model != settings_for(role, base, session=session).embedding_model:
            job = start_switch(session, row)
            session.commit()
            queue.submit(run_embedding_switch, job.id)
            return
    existing = load_row(session, role)
    if existing is not None:
        session.delete(existing)
        session.flush()
    if any((row.provider, row.model, row.base_url, row.api_key_encrypted)):
        session.add(row)
    session.commit()


def _effective(
    session: Session, role: ModelRole, body: RoleSettingsUpdate
) -> tuple[Settings, ModelSettingRow]:
    if body.provider is not None:
        if body.provider not in {p.value for p in LLMProvider if p is not LLMProvider.NONE}:
            raise DomainRuleError(f"Unknown provider {body.provider!r}.")
        spec = provider_spec(LLMProvider(body.provider), get_settings())
        if role is ModelRole.EMBEDDINGS and not spec.embeds:
            raise DomainRuleError(f"{spec.label} offers no embedding models.")
    base = routed(session, role=role)
    row = candidate(
        load_row(session, role),
        provider=body.provider,
        model=body.model,
        base_url=body.base_url,
        api_key=SecretStr(body.api_key) if body.api_key else None,
        clear_api_key=body.clear_api_key,
        settings=base,
    ).as_row(role)
    return apply_row(base, role, row, provider_configs(session, base)), row


def _provider_out(config: ProviderConfig) -> ProviderOut:
    spec = config.spec
    return ProviderOut(
        id=spec.id.value,
        label=spec.label,
        base_url=config.base_url,
        base_url_required=spec.base_url is None,
        api_key_masked=mask_key(config.api_key),
        chat_model=config.chat_model,
        embedding_model=spec.embedding_model,
        embeds=spec.embeds,
        lists_models=spec.listing != "none",
        configured=config.configured,
        saved=sorted(config.saved),
    )


@router.get("", response_model=ModelSettingsResponse)
def read_settings(session: DbSession, user: CurrentUser) -> ModelSettingsResponse:
    env = get_settings()
    route, saved = load_route(session, env)
    return ModelSettingsResponse(
        roles=[_describe(session, role) for role in ModelRole],
        providers=[_provider_out(c) for c in provider_configs(session, env).values()],
        can_edit=can_edit(user),
        route=route,
        route_source="db" if saved else "env",
    )


@router.put("/route", response_model=ModelSettingsResponse)
def set_route(body: RouteUpdate, session: DbSession, user: AdminUser) -> ModelSettingsResponse:
    """Make a provider the default every role follows unless it names its own.

    No Test is asked for, unlike a role save: the provider was tested when it was set up, and
    switching back is one click. A provider without a URL and key is refused, OpenRouter aside.
    """
    config = provider_configs(session)[LLMProvider(body.route)]
    # OpenRouter is the built-in default, so going back to it is always allowed.
    if not config.configured and config.spec.id is not LLMProvider.OPENROUTER:
        raise DomainRuleError(
            f"{config.spec.label} is not set up.",
            detail="Add its API key (and URL, where it needs one) under Providers first.",
        )
    save_route(session, body.route, user.id)
    return read_settings(session, user)


def _candidate_provider(
    session: Session, provider: LLMProvider, body: ProviderUpdate
) -> ProviderConfig:
    """The provider as it would be after ``body``: new values, else saved ones, else .env."""
    env = get_settings()
    saved = session.get(ModelSettingRow, PROVIDER_PREFIX + provider.value)
    row = ModelSettingRow(
        role=PROVIDER_PREFIX + provider.value,
        base_url=body.base_url or None,
        model=body.chat_model or None,
        api_key_encrypted=saved.api_key_encrypted if saved else None,
    )
    config = provider_config(env, provider, row)
    if body.api_key:
        config = ProviderConfig(
            config.spec, config.base_url, SecretStr(body.api_key), config.chat_model, config.saved
        )
    return config


@router.put("/providers/{provider}", response_model=ModelSettingsResponse)
def save_provider_settings(
    provider: LLMProvider, body: ProviderUpdate, session: DbSession, user: AdminUser
) -> ModelSettingsResponse:
    """Save a provider's URL, key and default model, after one test call proves they work.

    Nothing is saved when the call fails; the provider's own message comes back instead.
    """
    if provider is LLMProvider.NONE:
        raise DomainRuleError("Pick a provider.")
    config = _candidate_provider(session, provider, body)
    if not config.base_url:
        raise DomainRuleError(f"{config.spec.label} needs its endpoint URL.")
    if config.api_key is None:
        raise DomainRuleError(f"Enter an API key for {config.spec.label}.")
    if not config.chat_model:
        raise DomainRuleError(f"Choose a default model for {config.spec.label}.")
    result = probe(on_provider(get_settings(), config), embeddings=False)
    if not result.ok:
        raise DomainRuleError(
            f"{config.spec.label} did not answer the test call; nothing was saved.",
            detail=result.error,
        )
    save_provider(
        session,
        provider,
        base_url=body.base_url or None,
        api_key=SecretStr(body.api_key) if body.api_key else None,
        chat_model=body.chat_model or None,
        user_id=user.id,
    )
    _forget_models(provider)
    return read_settings(session, user)


@router.delete("/providers/{provider}", response_model=ModelSettingsResponse)
def reset_provider_settings(
    provider: LLMProvider, session: DbSession, user: AdminUser
) -> ModelSettingsResponse:
    """Forget a provider's saved values; whatever ``.env`` has for it applies again."""
    clear_provider(session, provider)
    _forget_models(provider)
    return read_settings(session, user)


def _per_million(pricing: object, key: str) -> float | None:
    """OpenRouter prices are USD-per-token strings; the picker shows USD per million tokens."""
    try:
        value = float(pricing[key])  # type: ignore[index]
    except (TypeError, KeyError, ValueError):
        return None
    return round(value * 1_000_000, 4) if value >= 0 else None


def _provider_model(raw: dict) -> ProviderModel:
    context = raw.get("context_length")
    pricing = raw.get("pricing")
    return ProviderModel(
        id=raw["id"],
        name=raw.get("name") or raw["id"],
        context_length=context if isinstance(context, int) and context > 0 else None,
        prompt_price=_per_million(pricing, "prompt"),
        completion_price=_per_million(pricing, "completion"),
    )


def _forget_models(provider: LLMProvider) -> None:
    for key in [k for k in _MODEL_CACHE if k.split("|", 1)[0] == provider.value]:
        del _MODEL_CACHE[key]


def _fetch_models(config: ProviderConfig) -> list[ProviderModel]:
    """Read the provider's model list. OpenRouter's is public and carries prices."""
    spec = config.spec
    if spec.id is LLMProvider.OPENROUTER:
        response = httpx.get(f"{OPENROUTER_BASE_URL}/models", timeout=15.0)
        response.raise_for_status()
        return [_provider_model(m) for m in response.json()["data"] if "id" in m]
    if not config.configured:
        raise DomainRuleError(
            f"{spec.label} is not set up.", detail="Add its API key under Providers first."
        )
    assert config.api_key is not None and config.base_url is not None
    key = config.api_key.get_secret_value()
    url = config.base_url.rstrip("/") + "/models"
    if spec.listing == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": _ANTHROPIC_VERSION}
        response = httpx.get(url, params={"limit": 1000}, headers=headers, timeout=15.0)
        response.raise_for_status()
        data = response.json()["data"]
        return [ProviderModel(id=m["id"], name=m.get("display_name") or m["id"]) for m in data]
    response = httpx.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=15.0)
    response.raise_for_status()
    return [ProviderModel(id=m["id"], name=m["id"]) for m in response.json()["data"] if "id" in m]


@router.get("/models", response_model=list[ProviderModel])
def provider_models(
    session: DbSession, provider: Annotated[LLMProvider, Query()] = LLMProvider.OPENROUTER
) -> list[ProviderModel]:
    """The provider's model ids for the picker; any other id can still be typed.

    Azure lists deployments only through its management API, so it has no list here.
    """
    if provider is LLMProvider.NONE:
        raise DomainRuleError("Pick a provider.")
    config = provider_configs(session)[provider]
    if config.spec.listing == "none":
        return []
    # The endpoint and key are part of the cache key: a custom URL or a new key lists anew.
    secret = config.api_key.get_secret_value() if config.api_key else ""
    fingerprint = hashlib.sha256(f"{config.base_url}|{secret}".encode()).hexdigest()[:16]
    cache_key = (
        provider.value if provider is LLMProvider.OPENROUTER else f"{provider.value}|{fingerprint}"
    )
    cached = _MODEL_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < _MODEL_CACHE_SECONDS:
        return cached[1]
    try:
        models = sorted(_fetch_models(config), key=lambda m: m.id)
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise LLMRequestError(
            "Could not fetch the provider's model list.", detail=str(exc)[:300]
        ) from exc
    _MODEL_CACHE[cache_key] = (time.monotonic(), models)
    return models


@router.post(
    "/{role}/test",
    response_model=SettingsTestResponse,
    dependencies=[Depends(require_admin)],
)
def test_settings(
    role: ModelRole, body: RoleSettingsUpdate, session: DbSession
) -> SettingsTestResponse:
    """One minimal call with the candidate configuration. Saves nothing."""
    if role in _UNTESTABLE:
        raise DomainRuleError(f"The {role.value} role can't be tested yet.")
    effective, _ = _effective(session, role, body)
    result = probe(effective, embeddings=role is ModelRole.EMBEDDINGS)
    return SettingsTestResponse(
        ok=result.ok,
        error=result.error,
        dimension=result.dimension,
        test_token=issue_test_token(role, effective) if result.ok else None,
    )


@router.put("/{role}", response_model=RoleSettingsResponse)
def save_settings(
    role: ModelRole,
    body: RoleSettingsSave,
    session: DbSession,
    user: AdminUser,
    queue: JobQueueDep,
) -> RoleSettingsResponse:
    effective, row = _effective(session, role, body)
    if not check_test_token(body.test_token, role, effective):
        raise DomainRuleError(
            "Test this configuration before saving it.",
            detail="The test token is missing, expired, or was issued for different settings.",
        )
    row.updated_by = user.id
    _save_or_switch(session, role, row, queue)
    return _describe(session, role)


@router.delete("/{role}", response_model=RoleSettingsResponse)
def reset_settings(
    role: ModelRole, session: DbSession, user: AdminUser, queue: JobQueueDep
) -> RoleSettingsResponse:
    """Use ``.env`` for every value again. For embeddings on another model, via a switch."""
    _save_or_switch(session, role, ModelSettingRow(role=role.value, updated_by=user.id), queue)
    return _describe(session, role)
