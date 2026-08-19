"""Async engine and session, used only by ``app/auth/``.

``fastapi-users``' SQLAlchemy adapter requires an ``AsyncSession``; every other
part of this application is synchronous (``app/persistence/database.py``), and
stays that way. This module opens a second connection to the *same* SQLite
file with the async ``aiosqlite`` driver purely so ``app/auth/`` can use that
library. Schema creation is still the sync engine's job (``database.init_db``)
-- both drivers read and write the same file, so nothing here needs its own
``create_all``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings, get_settings
from app.persistence.database import SQLITE_PREFIX, _ensure_sqlite_directory

logger = logging.getLogger(__name__)

_ASYNC_SQLITE_PREFIX = "sqlite+aiosqlite"

_async_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def _to_async_url(database_url: str) -> str:
    """Swap SQLite's sync driver for its async one; other backends must
    already name an async-capable driver in ``DATABASE_URL``."""
    if database_url.startswith(f"{SQLITE_PREFIX}:///"):
        return database_url.replace(SQLITE_PREFIX, _ASYNC_SQLITE_PREFIX, 1)
    return database_url


def create_async_db_engine(settings: Settings | None = None) -> AsyncEngine:
    """Build a new async engine from settings. Prefer :func:`get_async_engine`."""
    settings = settings or get_settings()
    _ensure_sqlite_directory(settings.database_url)
    engine = create_async_engine(
        _to_async_url(settings.database_url), echo=settings.database_echo, future=True
    )
    logger.debug(
        "Async database engine created for %s", engine.url.render_as_string(hide_password=True)
    )
    return engine


def get_async_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_db_engine()
    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(bind=get_async_engine(), expire_on_commit=False)
    return _async_session_factory


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session per request, for ``app/auth/`` only."""
    async with get_async_session_factory()() as session:
        yield session


def reset_async_engine_for_testing() -> None:
    """Drop the cached async engine and session factory.

    Only for tests that change ``DATABASE_URL`` between cases. Skips the
    (async) ``dispose()`` call -- these are throwaway per-test SQLite files,
    and there is no synchronous context here to await it from.
    """
    global _async_engine, _async_session_factory
    _async_engine = None
    _async_session_factory = None
