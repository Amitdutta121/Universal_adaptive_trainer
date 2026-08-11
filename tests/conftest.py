"""Shared test fixtures.

Tests run against a temporary SQLite file and test-mode settings, so no test can
touch the developer's ``data/`` directory.

Settings are injected by setting environment variables and clearing the
``get_settings`` cache, rather than by patching the function: many modules do
``from app.config import get_settings``, so rebinding the attribute would leave
those references pointing at the original. Environment variables also take
precedence over a developer's ``.env``, which keeps results machine-independent.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.persistence import database

TEST_ENV: dict[str, str] = {
    "ENVIRONMENT": "test",
    "DEBUG": "true",
    "LOG_LEVEL": "WARNING",
    "DATABASE_ECHO": "false",
    "LLM_PROVIDER": "none",
    "LLM_API_KEY": "",
    "LLM_BASE_URL": "",
}


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Test settings pointing at a throwaway SQLite file."""
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("BOOK_UPLOAD_DIR", str(tmp_path / "books"))

    get_settings.cache_clear()
    database.reset_engine_for_testing()
    try:
        yield get_settings()
    finally:
        get_settings.cache_clear()
        database.reset_engine_for_testing()


@pytest.fixture
def configured_app(settings: Settings) -> FastAPI:
    """A FastAPI app wired to the test settings."""
    from app.main import create_app

    return create_app(settings)


@pytest.fixture
def client(configured_app: FastAPI) -> Iterator[TestClient]:
    """HTTP client that runs the app's lifespan, so the schema is created."""
    with TestClient(configured_app) as test_client:
        yield test_client


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    """A standalone engine with the schema created, for persistence-level tests."""
    test_engine = database.create_db_engine(settings)
    database.init_db(test_engine)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session bound to the test engine."""
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
