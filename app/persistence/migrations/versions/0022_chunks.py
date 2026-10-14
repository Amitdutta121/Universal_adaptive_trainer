"""Chunks: the flat, versioned source unit that replaces the chapter/section tree (Task 4).

Schema only. Existing books keep their sections and get no chunks (``current_version``
stays NULL); re-importing the file is how an old book gets chunks.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_chunks"
down_revision = "0021_solve_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("book_version", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("heading_path_json", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=True),
        sa.Column("end_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "book_version", "ordinal"),
    )
    op.create_index(op.f("ix_chunks_book_id"), "chunks", ["book_id"], unique=False)
    with op.batch_alter_table("books") as batch:
        batch.add_column(sa.Column("current_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("books") as batch:
        batch.drop_column("current_version")
    op.drop_index(op.f("ix_chunks_book_id"), table_name="chunks")
    op.drop_table("chunks")
