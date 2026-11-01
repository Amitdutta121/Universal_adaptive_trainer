"""Per-role model settings over ``.env`` (Task 41)."""

from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import LLMProvider, Settings
from app.llm import get_structured_client
from app.llm.availability import describe_availability
from app.persistence.models import ModelSettingRow
from app.retrieval import get_embedder
from app.settings_store import ModelRole, encrypt_api_key, settings_for

ENV_KEY = "sk-or-env-key"
DB_KEY = "sk-or-db-key-0123456789"


@pytest.fixture
def base(settings: Settings) -> Settings:
    """The ``.env`` defaults, with a key so clients can be built."""
    return settings.model_copy(
        update={"llm_provider": LLMProvider.OPENROUTER, "llm_api_key": SecretStr(ENV_KEY)}
    )


def _save(session: Session, role: ModelRole, base: Settings, **fields: object) -> None:
    key = fields.pop("api_key", None)
    row = ModelSettingRow(role=role.value, **fields)
    if key is not None:
        row.api_key_encrypted = encrypt_api_key(SecretStr(str(key)), base)
    session.add(row)
    session.commit()


def test_with_no_rows_every_role_is_the_env_settings(base: Settings, session: Session) -> None:
    for role in ModelRole:
        assert settings_for(role, base) is base
        assert settings_for(role, base, session=session) is base
    assert get_structured_client(base).description == f"openrouter/{base.llm_model}"
    assert get_embedder(base).model == base.embedding_model


def test_a_row_changes_only_its_own_role(base: Settings, session: Session) -> None:
    _save(session, ModelRole.GENERATION, base, model="anthropic/claude-haiku-4.5", api_key=DB_KEY)

    generation = settings_for(ModelRole.GENERATION, base)
    assert generation.llm_model == "anthropic/claude-haiku-4.5"
    assert generation.llm_api_key is not None
    assert generation.llm_api_key.get_secret_value() == DB_KEY
    for role in set(ModelRole) - {ModelRole.GENERATION}:
        assert settings_for(role, base) is base

    assert get_structured_client(base).description == "openrouter/anthropic/claude-haiku-4.5"
    judges = get_structured_client(base, role=ModelRole.JUDGES)
    assert judges.description == f"openrouter/{base.llm_model}"


def test_empty_fields_keep_env_and_embeddings_set_the_embedding_model(
    base: Settings, session: Session
) -> None:
    _save(session, ModelRole.EMBEDDINGS, base, model="openai/text-embedding-3-large")

    embeddings = settings_for(ModelRole.EMBEDDINGS, base)
    assert embeddings.embedding_model == "openai/text-embedding-3-large"
    assert embeddings.llm_model == base.llm_model
    assert embeddings.llm_api_key == base.llm_api_key  # no key in the row: the .env one
    assert get_embedder(base).model == "openai/text-embedding-3-large"


def test_a_db_key_configures_llm_features_without_an_env_key(
    settings: Settings, session: Session
) -> None:
    assert settings.llm_api_key is None
    _save(session, ModelRole.GENERATION, settings, provider="openrouter", api_key=DB_KEY)

    configured, status = describe_availability(settings)
    assert configured
    assert DB_KEY not in status


def test_keys_are_never_plaintext_in_the_db_repr_or_logs(
    base: Settings, session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _save(session, ModelRole.GENERATION, base, api_key=DB_KEY)

    stored = session.execute(text("SELECT api_key_encrypted FROM model_settings")).scalar_one()
    assert DB_KEY.encode() not in stored
    resolved = settings_for(ModelRole.GENERATION, base)
    row = session.get(ModelSettingRow, "generation")
    assert DB_KEY not in repr(resolved)
    assert DB_KEY not in repr(row)
    assert DB_KEY not in resolved.describe_llm()
    assert DB_KEY not in caplog.text


def test_a_changed_server_secret_falls_back_to_the_env_key(
    base: Settings, session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    _save(session, ModelRole.GENERATION, base, model="x/y", api_key=DB_KEY)
    rotated = base.model_copy(update={"auth_secret_key": SecretStr("another-secret-entirely")})

    resolved = settings_for(ModelRole.GENERATION, rotated)

    assert resolved.llm_model == "x/y"
    assert resolved.llm_api_key is not None
    assert resolved.llm_api_key.get_secret_value() == ENV_KEY
    assert "can't be decrypted" in caplog.text
    assert DB_KEY not in caplog.text


def test_a_database_without_the_table_has_no_rows(base: Settings) -> None:
    # The ``settings`` fixture's database file exists but no migration has run on it.
    assert settings_for(ModelRole.GENERATION, base) is base
