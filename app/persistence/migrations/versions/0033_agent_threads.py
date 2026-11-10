"""Saved conversations with the course assistant, per course and professor (ADR-075)."""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "0033_agent_threads"
down_revision = "0032_hidden_question_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_threads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey(
                "courses.id", ondelete="CASCADE", name="fk_agent_threads_course_id_courses"
            ),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            GUID(),
            sa.ForeignKey("user.id", ondelete="CASCADE", name="fk_agent_threads_owner_id_user"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("messages_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_threads_course_id", "agent_threads", ["course_id"])
    op.create_index("ix_agent_threads_owner_id", "agent_threads", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_threads_owner_id", table_name="agent_threads")
    op.drop_index("ix_agent_threads_course_id", table_name="agent_threads")
    op.drop_table("agent_threads")
