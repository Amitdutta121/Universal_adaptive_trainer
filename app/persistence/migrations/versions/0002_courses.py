"""Courses: a ``courses`` table, and ``course_id`` on books and curriculum versions.

Every existing book and curriculum version is moved into one "Default course",
owned by the first professor account if there is one, so nothing already built
disappears from view.

Revision ID: 0002_courses
Revises: 0001_baseline
Create Date: 2026-10-01
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "0002_courses"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

DEFAULT_COURSE_NAME = "Default course"


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "owner_id",
            GUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_courses_owner_id", "courses", ["owner_id"])

    for table in ("books", "curriculum_versions"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("course_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_course_id", "courses", ["course_id"], ["id"])
            batch.create_index(f"ix_{table}_course_id", ["course_id"])

    bind = op.get_bind()
    has_content = any(
        bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None
        for table in ("books", "curriculum_versions")
    )
    if not has_content:
        return
    owner = bind.execute(sa.text('SELECT id FROM "user" ORDER BY email LIMIT 1')).scalar()
    courses = sa.table(
        "courses",
        sa.column("name", sa.String),
        sa.column("owner_id", GUID()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    bind.execute(
        courses.insert().values(
            name=DEFAULT_COURSE_NAME, owner_id=owner, created_at=datetime.now(UTC)
        )
    )
    course_id = bind.execute(sa.text("SELECT max(id) FROM courses")).scalar_one()
    for table in ("books", "curriculum_versions"):
        bind.execute(sa.text(f"UPDATE {table} SET course_id = :id"), {"id": course_id})


def downgrade() -> None:
    for table in ("books", "curriculum_versions"):
        with op.batch_alter_table(table) as batch:
            # No drop_constraint: the foreign key is unnamed when ``create_all``
            # built the table, and the batch rebuild drops it with the column.
            batch.drop_index(f"ix_{table}_course_id")
            batch.drop_column("course_id")
    op.drop_index("ix_courses_owner_id", "courses")
    op.drop_table("courses")
