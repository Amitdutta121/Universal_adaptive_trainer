"""Model settings per role: read, test, save, reset, and the provider's model list (Task 42).

Any signed-in professor can read the settings (keys masked). Testing, saving and resetting
change what the whole instance spends money on, so they need an admin (a superuser).
Saving needs the token from a passing Test of exactly the configuration being saved.
"""

from __future__ import annotations

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
from app.llm.client import OPENROUTER_BASE_URL
from app.llm.probe import probe
from app.persistence.models import ModelSettingRow, UserRow
from app.retrieval.reembed import run_embedding_switch, start_switch, switch_job
from app.settings_store import (
    ModelRole,
    apply_row,
    candidate,
    check_test_token,
    decrypt_api_key,
    issue_test_token,
    load_route,
    load_row,
    mask_key,
    routed,
    save_route,
    settings_for,
)
from app.web.routes.api.deps import CurrentUser, DbSession
from app.web.routes.api.schemas import (
    EmbeddingSwitchOut,
    ModelSettingsResponse,
    ProviderModel,
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
#: Provider model lists, refreshed hourly: ``{provider: (fetched_at, models)}``.
_MODEL_CACHE: dict[str, tuple[float, list[ProviderModel]]] = {}
_MODEL_CACHE_SECONDS = 3600


def require_admin(user: CurrentUser) -> UserRow:
    if not user.is_superuser:
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


def _describe(session: Session, role: ModelRole, base: Settings) -> RoleSettingsResponse:
    row = load_row(session, role)
    effective = apply_row(base, role, row)
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
        base = routed(session)
        new_model = apply_row(base, role, row).embedding_model
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
    if body.provider is not None and body.provider not in {p.value for p in LLMProvider}:
        raise DomainRuleError(f"Unknown provider {body.provider!r}.")
    base = routed(session)
    row = candidate(
        load_row(session, role),
        provider=body.provider,
        model=body.model,
        base_url=body.base_url,
        api_key=SecretStr(body.api_key) if body.api_key else None,
        clear_api_key=body.clear_api_key,
        settings=base,
    ).as_row(role)
    return apply_row(base, role, row), row


@router.get("", response_model=ModelSettingsResponse)
def read_settings(session: DbSession, user: CurrentUser) -> ModelSettingsResponse:
    env = get_settings()
    route, saved = load_route(session, env)
    base = env.on_route(route)
    return ModelSettingsResponse(
        roles=[_describe(session, role, base) for role in ModelRole],
        providers=[p.value for p in LLMProvider if p is not LLMProvider.NONE],
        can_edit=user.is_superuser,
        route=route,
        route_source="db" if saved else "env",
        azure_configured=env.azure_configured,
    )


@router.put("/route", response_model=ModelSettingsResponse)
def set_route(body: RouteUpdate, session: DbSession, user: AdminUser) -> ModelSettingsResponse:
    """Point every role without its own saved settings at OpenRouter or Azure.

    No Test is asked for, unlike a role save: both routes come from ``.env`` as configured,
    and switching back is one click. Azure is refused while its URL or key is missing.
    """
    if body.route == "azure" and not get_settings().azure_configured:
        raise DomainRuleError(
            "Azure is not configured.",
            detail="Set AZURE_BASE_URL and AZURE_API_KEY in .env, then restart the backend.",
        )
    save_route(session, body.route, user.id)
    return read_settings(session, user)


@router.get("/models", response_model=list[ProviderModel])
def provider_models(provider: str = Query(default="openrouter")) -> list[ProviderModel]:
    """The provider's model ids for the picker; any other id can still be typed."""
    if provider != LLMProvider.OPENROUTER.value:
        raise DomainRuleError(f"No model list for provider {provider!r}.")
    cached = _MODEL_CACHE.get(provider)
    if cached and time.monotonic() - cached[0] < _MODEL_CACHE_SECONDS:
        return cached[1]
    try:
        response = httpx.get(f"{OPENROUTER_BASE_URL}/models", timeout=15.0)
        response.raise_for_status()
        data = response.json()["data"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise LLMRequestError(
            "Could not fetch the provider's model list.", detail=str(exc)[:300]
        ) from exc
    models = sorted(
        (ProviderModel(id=m["id"], name=m.get("name") or m["id"]) for m in data if "id" in m),
        key=lambda m: m.id,
    )
    _MODEL_CACHE[provider] = (time.monotonic(), models)
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
    return _describe(session, role, routed(session))


@router.delete("/{role}", response_model=RoleSettingsResponse)
def reset_settings(
    role: ModelRole, session: DbSession, user: AdminUser, queue: JobQueueDep
) -> RoleSettingsResponse:
    """Use ``.env`` for every value again. For embeddings on another model, via a switch."""
    _save_or_switch(session, role, ModelSettingRow(role=role.value, updated_by=user.id), queue)
    return _describe(session, role, routed(session))
