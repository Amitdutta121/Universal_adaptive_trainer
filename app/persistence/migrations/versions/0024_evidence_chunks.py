"""Subtopic evidence points at a chunk (Task 8).

``chunk_id`` is added and ``section_id`` becomes nullable. No data is copied: evidence
rows from before chunks keep their section id and get no chunk.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_evidence_chunks"
down_revision = "0023_chunk_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subtopic_evidence") as batch:
        batch.add_column(sa.Column("chunk_id", sa.String(length=32), nullable=True))
        batch.alter_column("section_id", existing_type=sa.Integer(), nullable=True)
        batch.create_index(batch.f("ix_subtopic_evidence_chunk_id"), ["chunk_id"], unique=False)
        batch.create_foreign_key(
            "fk_subtopic_evidence_chunk_id_chunks",
            "chunks",
            ["chunk_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("subtopic_evidence") as batch:
        batch.drop_constraint("fk_subtopic_evidence_chunk_id_chunks", type_="foreignkey")
        batch.drop_index(batch.f("ix_subtopic_evidence_chunk_id"))
        batch.alter_column("section_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("chunk_id")
