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

#: Row key of the instance's route (``provider`` holds ``openrouter`` or ``azure``), set by the
#: Settings screen's toggle over ``LLM_ROUTE``. Like ``PENDING_EMBEDDINGS``, never a role.
ROUTE = "route"

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


def apply_row(base: Settings, role: ModelRole, row: ModelSettingRow | None) -> Settings:
    """``base`` with the fields ``row`` sets replacing the ones it overrides for ``role``."""
    if row is None:
        return base
    update: dict[str, object] = {}
    if row.provider:
        update["llm_provider"] = LLMProvider(row.provider)
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


def routed(session: Session, base: Settings | None = None) -> Settings:
    """``base`` (``get_settings()``) on the instance's route, before any role's own row."""
    base = base or get_settings()
    try:
        route, _ = load_route(session, base)
    except OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        route = base.llm_route
    return base.on_route(route)


def settings_for(
    role: ModelRole, base: Settings | None = None, *, session: Session | None = None
) -> Settings:
    """The effective settings for ``role``: its database row over ``base`` (``get_settings()``)
    on the instance's route (:func:`routed`).

    Without ``session``, reads through a short session of the app database. A database
    without the table yet (before migrations ran) counts as having no rows.
    """
    base = base or get_settings()
    if session is not None:
        return apply_row(routed(session, base), role, load_row(session, role))
    from app.persistence.database import get_session_factory

    try:
        with get_session_factory()() as own:
            base = routed(own, base)
            row = load_row(own, role)
    except OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        row = None
    return apply_row(base, role, row)


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
