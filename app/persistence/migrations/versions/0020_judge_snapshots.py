"""Frozen judge-memory snapshots for a round (ADR-064, m11)."""

import sqlalchemy as sa
from alembic import op

revision = "0020_judge_snapshots"
down_revision = "0019_audit_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "judge_memory_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject", sa.String(length=50), nullable=False),
        sa.Column("guidelines_json", sa.Text(), nullable=False),
        sa.Column("promoted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_judge_memory_snapshots_subject", "judge_memory_snapshots", ["subject"])
    with op.batch_alter_table("generation_rounds") as batch:
        batch.add_column(sa.Column("judge_snapshot_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_generation_rounds_judge_snapshot_id",
            "judge_memory_snapshots",
            ["judge_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("generation_rounds") as batch:
        batch.drop_constraint("fk_generation_rounds_judge_snapshot_id", type_="foreignkey")
        batch.drop_column("judge_snapshot_id")
    op.drop_index("ix_judge_memory_snapshots_subject", table_name="judge_memory_snapshots")
    op.drop_table("judge_memory_snapshots")
