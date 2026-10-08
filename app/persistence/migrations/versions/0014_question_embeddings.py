"""Question embeddings for the duplicate check inside rounds (ADR-063 point 6).

A derived cache, filled lazily the first time a question is compared against; nothing to
backfill here.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_question_embeddings"
down_revision = "0013_lessons_round"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_question_embeddings_question_id"),
        "question_embeddings",
        ["question_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_question_embeddings_question_id"), table_name="question_embeddings")
    op.drop_table("question_embeddings")
