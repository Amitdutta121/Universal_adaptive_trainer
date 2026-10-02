"""Baseline: the schema as ``create_all`` built it before migrations existed.

Deliberately empty. A database that predates Alembic is stamped at this revision
by ``init_db`` and then upgraded; a brand-new database is built by ``create_all``
and stamped at head. Neither path needs this revision to create anything.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-01
"""

from __future__ import annotations

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
