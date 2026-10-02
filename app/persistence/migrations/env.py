"""Alembic environment.

Only ever run in-process by :func:`app.persistence.database.init_db`, which hands
over a live connection through ``config.attributes["connection"]``. There is no
``alembic.ini`` and no offline (SQL script) mode: the app owns its schema and
upgrades it on start.
"""

from __future__ import annotations

from alembic import context

from app.persistence import models  # noqa: F401  (registers mappers)
from app.persistence.database import Base

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    # SQLite cannot ALTER most things in place; batch mode rebuilds the table.
    render_as_batch=True,
)
with context.begin_transaction():
    context.run_migrations()
