"""Alembic environment.

``init_db`` runs migrations in-process and hands over its live connection through
``config.attributes["connection"]``. Run from the command line instead
(``alembic upgrade head``, ``alembic check``, ``alembic revision --autogenerate``
via the repo-root ``alembic.ini``), it connects to ``DATABASE_URL`` from
:mod:`app.config`. There is no offline (SQL script) mode.
"""

from __future__ import annotations

from alembic import context

from app.persistence import models  # noqa: F401  (registers mappers)
from app.persistence.database import Base, create_db_engine


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        # SQLite cannot ALTER most things in place; batch mode rebuilds the table.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:
    engine = create_db_engine()
    with engine.begin() as connection:
        _run(connection)
    engine.dispose()
