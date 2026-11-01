"""Model settings chosen per role, stored in the database over the ``.env`` defaults (Task 41).

Each role (generation, judges, ...) may have one ``model_settings`` row. Any field it sets
replaces the matching ``.env`` value for that role only; a field left empty keeps ``.env``, so
a row can switch the model and still use the ``.env`` key. With no row, a role's settings are
exactly ``get_settings()``.

API keys are stored Fernet-encrypted with a key derived (HKDF) from ``AUTH_SECRET_KEY``, so no
second secret has to be managed. Changing ``AUTH_SECRET_KEY`` makes stored keys unreadable:
the role then falls back to the ``.env`` key with a warning and the key must be saved again.
Keys only ever live in memory as ``SecretStr``, which masks them in ``repr`` and logs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import get_args

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import LLMProvider, LLMRoute, Settings, get_settings
from app.llm_providers import OPENROUTER_BASE_URL, ProviderSpec, env_credentials, provider_spec
from app.persistence.models import ModelSettingRow

logger = logging.getLogger(__name__)


class ModelRole(StrEnum):
    """What a model is used for; each can be pointed at its own provider and model."""

    GENERATION = "generation"
    JUDGES = "judges"
    AGENT = "agent"
    TUTORIALS = "tutorials"
    ASK_WHY = "ask_why"
    EMBEDDINGS = "embeddings"
    TRANSCRIPTION = "transcription"


#: Row key of an embeddings configuration waiting for its re-embedding job (Task 43). Never
#: read by :func:`settings_for`: retrieval stays on the active model until the job swaps it in.
PENDING_EMBEDDINGS = "embeddings.pending"

#: Row key of the instance's default provider (``provider`` holds its id), chosen on the
#: Settings screen over ``LLM_ROUTE``. Like ``PENDING_EMBEDDINGS``, never a role.
ROUTE = "route"

#: Row key prefix of a provider's saved URL, key and default chat model (ADR-068):
#: ``provider.openai`` and so on. Never a role either.
PROVIDER_PREFIX = "provider."

_HKDF_INFO = b"adaptive-trainer/model-settings/api-key"


def _fernet(settings: Settings) -> Fernet:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        settings.auth_secret_key.get_secret_value().encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_api_key(api_key: SecretStr, settings: Settings | None = None) -> bytes:
    return _fernet(settings or get_settings()).encrypt(api_key.get_secret_value().encode())


def decrypt_api_key(token: bytes, settings: Settings | None = None) -> SecretStr:
    """Raises ``InvalidToken`` when ``AUTH_SECRET_KEY`` changed since the key was saved."""
    return SecretStr(_fernet(settings or get_settings()).decrypt(token).decode())


def load_row(session: Session, role: ModelRole) -> ModelSettingRow | None:
    return session.scalars(select(ModelSettingRow).where(ModelSettingRow.role == role)).first()


# -- Providers (ADR-068) ----------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderConfig:
    """One provider as the app will call it: ``.env`` values with any saved ones on top."""

    spec: ProviderSpec
    base_url: str | None
    api_key: SecretStr | None
    #: The chat model a role on this provider uses when it names none.
    chat_model: str | None
    #: Which of base_url, api_key and chat_model were saved on the Settings screen.
    saved: frozenset[str]

    @property
    def configured(self) -> bool:
        return bool(self.base_url) and self.api_key is not None


def _provider_row(session: Session, provider: LLMProvider) -> ModelSettingRow | None:
    return session.get(ModelSettingRow, PROVIDER_PREFIX + provider.value)


def provider_config(
    env: Settings, provider: LLMProvider, row: ModelSettingRow | None
) -> ProviderConfig:
    spec = provider_spec(provider, env)
    base_url, api_key = env_credentials(provider, env)
    model = spec.chat_model
    saved: set[str] = set()
    if row is not None:
        if row.base_url:
            base_url = row.base_url
            saved.add("base_url")
        if row.api_key_encrypted:
            try:
                api_key = decrypt_api_key(row.api_key_encrypted, env)
                saved.add("api_key")
            except InvalidToken:
                logger.warning(
                    "The stored %s key can't be decrypted (AUTH_SECRET_KEY changed?); using "
                    "the .env key until it is saved again.",
                    provider.value,
                )
        if row.model:
            model = row.model
            saved.add("chat_model")
    return ProviderConfig(spec, base_url, api_key, model, frozenset(saved))


def provider_configs(
    session: Session, env: Settings | None = None
) -> dict[LLMProvider, ProviderConfig]:
    """Every provider, ``.env`` values with saved ones on top. No table yet means none saved."""
    env = env or get_settings()
    providers = [p for p in LLMProvider if p is not LLMProvider.NONE]
    try:
        rows = {p: _provider_row(session, p) for p in providers}
    except OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        rows = dict.fromkeys(providers)
    return {p: provider_config(env, p, rows[p]) for p in providers}


def save_provider(
    session: Session,
    provider: LLMProvider,
    *,
    base_url: str | None,
    api_key: SecretStr | None,
    chat_model: str | None,
    user_id: uuid.UUID | None,
    settings: Settings | None = None,
) -> None:
    """Store a provider's values. ``api_key=None`` keeps the stored key; empty values keep .env."""
    key = PROVIDER_PREFIX + provider.value
    row = session.get(ModelSettingRow, key) or ModelSettingRow(role=key)
    row.provider = provider.value
    row.base_url = base_url
    row.model = chat_model
    if api_key is not None:
        row.api_key_encrypted = encrypt_api_key(api_key, settings)
    row.updated_by = user_id
    session.add(row)
    session.commit()


def clear_provider(session: Session, provider: LLMProvider) -> None:
    """Forget a provider's saved values: it is back to whatever ``.env`` has."""
    row = _provider_row(session, provider)
    if row is not None:
        session.delete(row)
        session.commit()


def on_provider(base: Settings, config: ProviderConfig) -> Settings:
    """``base`` calling ``config``'s provider: its endpoint, key and default models."""
    update: dict[str, object] = {
        "llm_provider": config.spec.id,
        "llm_base_url": config.base_url,
        "llm_api_key": config.api_key,
    }
    if config.chat_model:
        update["llm_model"] = config.chat_model
    if config.spec.embedding_model:
        update["embedding_model"] = config.spec.embedding_model
    # OpenRouter's own URL is what an unset LLM_BASE_URL already means.
    if base.llm_base_url is None and config.base_url == OPENROUTER_BASE_URL:
        update["llm_base_url"] = None
    changed = {k: v for k, v in update.items() if getattr(base, k) != v}
    # Unchanged settings stay the very same object: no provider saved means exactly ``.env``.
    return base.model_copy(update=changed) if changed else base


def apply_row(
    base: Settings,
    role: ModelRole,
    row: ModelSettingRow | None,
    configs: dict[LLMProvider, ProviderConfig] | None = None,
) -> Settings:
    """``base`` with the fields ``row`` sets replacing the ones it overrides for ``role``.

    A row naming a provider moves the role onto it (given ``configs``: that provider's URL,
    key and default models); the row's model then replaces the provider's default.
    """
    if row is None:
        return base
    update: dict[str, object] = {}
    if row.provider:
        provider = LLMProvider(row.provider)
        if configs is not None and provider in configs:
            base = on_provider(base, configs[provider])
        else:
            update["llm_provider"] = provider
    if row.model:
        update["embedding_model" if role is ModelRole.EMBEDDINGS else "llm_model"] = row.model
    if row.base_url:
        update["llm_base_url"] = row.base_url
    if row.api_key_encrypted:
        try:
            update["llm_api_key"] = decrypt_api_key(row.api_key_encrypted, base)
        except InvalidToken:
            logger.warning(
                "The stored API key for the %s role can't be decrypted (AUTH_SECRET_KEY "
                "changed?); using the .env key until it is saved again.",
                role.value,
            )
    return base.model_copy(update=update) if update else base


def load_route(session: Session, base: Settings) -> tuple[LLMRoute, bool]:
    """The route in effect, and whether it was saved here (``True``) or is ``LLM_ROUTE``."""
    row = session.get(ModelSettingRow, ROUTE)
    if row is not None and row.provider in get_args(LLMRoute):
        return row.provider, True  # type: ignore[return-value]
    return base.llm_route, False


def save_route(session: Session, route: LLMRoute, user_id: uuid.UUID | None) -> None:
    row = session.get(ModelSettingRow, ROUTE) or ModelSettingRow(role=ROUTE)
    row.provider = route
    row.updated_by = user_id
    session.add(row)
    session.commit()


def default_provider_for(route: LLMRoute, role: ModelRole | None, env: Settings) -> LLMProvider:
    """The provider a role follows by default. Embeddings stay on OpenRouter when the default
    provider has no embedding model to offer (Claude, Grok, DeepSeek, custom)."""
    provider = LLMProvider(route)
    if role is ModelRole.EMBEDDINGS and provider_spec(provider, env).embedding_model is None:
        return LLMProvider.OPENROUTER
    return provider


def routed(
    session: Session, base: Settings | None = None, role: ModelRole | None = None
) -> Settings:
    """``base`` (``get_settings()``) on the default provider, before any role's own row."""
    base = base or get_settings()
    try:
        route, _ = load_route(session, base)
    except OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        route = base.llm_route
    provider = default_provider_for(route, role, base)
    return on_provider(base, provider_configs(session, base)[provider])


def settings_for(
    role: ModelRole, base: Settings | None = None, *, session: Session | None = None
) -> Settings:
    """The effective settings for ``role``: its database row over ``base`` (``get_settings()``)
    on the default provider (:func:`routed`).

    Without ``session``, reads through a short session of the app database. A database
    without the table yet (before migrations ran) counts as having no rows.
    """
    base = base or get_settings()
    if session is None:
        from app.persistence.database import get_session_factory

        with get_session_factory()() as own:
            return settings_for(role, base, session=own)
    try:
        row = load_row(session, role)
    except OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        row = None
    return apply_row(routed(session, base, role), role, row, provider_configs(session, base))


# -- Settings API support (Task 42) -----------------------------------------------------------

#: How long a passing Test lets that exact configuration be saved.
TEST_TOKEN_TTL_SECONDS = 30 * 60
_TOKEN_INFO = b"adaptive-trainer/model-settings/test-token"


@dataclass(frozen=True)
class Candidate:
    """A role's row as it would be after an edit; never persisted until saved."""

    provider: str | None
    model: str | None
    base_url: str | None
    api_key_encrypted: bytes | None

    def as_row(self, role: ModelRole) -> ModelSettingRow:
        return ModelSettingRow(
            role=role.value,
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            api_key_encrypted=self.api_key_encrypted,
        )


def candidate(
    existing: ModelSettingRow | None,
    *,
    provider: str | None,
    model: str | None,
    base_url: str | None,
    api_key: SecretStr | None,
    clear_api_key: bool,
    settings: Settings | None = None,
) -> Candidate:
    """The edit applied to ``existing``. ``api_key=None`` keeps the stored key."""
    if clear_api_key:
        key = None
    elif api_key is not None:
        key = encrypt_api_key(api_key, settings)
    else:
        key = existing.api_key_encrypted if existing else None
    return Candidate(provider=provider, model=model, base_url=base_url, api_key_encrypted=key)


def mask_key(key: SecretStr | None) -> str | None:
    """``••••abcd``: enough to tell keys apart, never enough to use one."""
    if key is None:
        return None
    value = key.get_secret_value()
    return "••••" + value[-4:] if len(value) > 8 else "••••"


def _signing_key(settings: Settings) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_TOKEN_INFO).derive(
        settings.auth_secret_key.get_secret_value().encode()
    )


def _fingerprint(role: ModelRole, effective: Settings) -> str:
    key = effective.llm_api_key.get_secret_value() if effective.llm_api_key else ""
    model = effective.embedding_model if role is ModelRole.EMBEDDINGS else effective.llm_model
    parts = [
        role.value,
        effective.llm_provider.value,
        model,
        effective.llm_base_url or "",
        hashlib.sha256(key.encode()).hexdigest(),
    ]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def issue_test_token(role: ModelRole, effective: Settings, *, now: float | None = None) -> str:
    """Proof that ``effective`` passed a Test, bound to that exact configuration."""
    expires = int((now or time.time()) + TEST_TOKEN_TTL_SECONDS)
    body = f"{expires}.{_fingerprint(role, effective)}"
    signature = hmac.new(_signing_key(effective), body.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def check_test_token(
    token: str, role: ModelRole, effective: Settings, *, now: float | None = None
) -> bool:
    """True when ``token`` was issued for this configuration and has not expired."""
    expires, _, signature = token.partition(".")
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return False
    body = f"{expires}.{_fingerprint(role, effective)}"
    expected = hmac.new(_signing_key(effective), body.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
