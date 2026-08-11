"""Engine, session and schema bootstrap.

SQLite via SQLAlchemy 2.0. The schema is created with ``create_all`` for now;
a migration tool will be introduced once the tables stop changing shape
(see ``docs/DECISIONS.md``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

SQLITE_PREFIX = "sqlite"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _ensure_sqlite_directory(database_url: str) -> None:
    """Create the parent directory of a file-backed SQLite database."""
    if not database_url.startswith(SQLITE_PREFIX):
        return
    _, _, path_part = database_url.partition(":///")
    if not path_part or path_part == ":memory:":
        return
    parent = Path(path_part).expanduser().parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Build a new engine from settings. Prefer :func:`get_engine` in app code."""
    settings = settings or get_settings()
    _ensure_sqlite_directory(settings.database_url)

    connect_args: dict[str, object] = {}
    if settings.database_url.startswith(SQLITE_PREFIX):
        # FastAPI serves requests from a thread pool; SQLite's default
        # same-thread check would reject those connections.
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.database_url,
        echo=settings.database_echo,
        future=True,
        connect_args=connect_args,
    )
    logger.debug("Database engine created for %s", engine.url.render_as_string(hide_password=True))
    return engine


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _session_factory


def init_db(engine: Engine | None = None) -> None:
    """Create any missing tables, then check existing ones are up to date.

    Safe to call repeatedly. Import of :mod:`app.persistence.models` is what
    registers the tables on :class:`Base`, so it happens here explicitly.
    """
    from app.persistence import models  # noqa: F401  (registers mappers)

    target = engine or get_engine()
    Base.metadata.create_all(bind=target)
    verify_schema(target)
    logger.info("Database schema ready (%d tables)", len(Base.metadata.tables))


def verify_schema(engine: Engine | None = None) -> None:
    """Fail loudly when an existing table is missing columns the models declare.

    ``create_all`` adds missing *tables* but never alters existing ones, so a
    database file created before a model gained a column would otherwise survive
    startup and fail later with a bare "no such column". There is no migration
    tool yet (see ``docs/DECISIONS.md`` ADR-008), so the honest response is to
    name the drift and the remedy.

    Raises:
        SchemaOutOfDateError: if any mapped column is absent from the database.
    """
    from app.errors import SchemaOutOfDateError

    target = engine or get_engine()
    inspector = inspect(target)
    existing_tables = set(inspector.get_table_names())

    drift: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        missing = [column.name for column in table.columns if column.name not in actual]
        drift.extend(f"{table_name}.{name}" for name in missing)

    if not drift:
        return

    url = target.url
    location = url.database or str(url)
    raise SchemaOutOfDateError(
        "The database file is older than the current data model.",
        detail=(
            f"Missing column(s): {', '.join(sorted(drift))}. There is no migration tool yet, "
            f"so delete the database file and let it be recreated on the next start: {location}"
        ),
    )


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context manager for non-request code and tests."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a read/write session per request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine_for_testing() -> None:
    """Drop the cached engine and session factory.

    Only for tests that change ``DATABASE_URL`` between cases.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
