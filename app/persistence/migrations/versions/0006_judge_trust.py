"""Durable automatic approval provenance and atomic audit sequencing."""

import sqlalchemy as sa
from alembic import op

revision = "0006_judge_trust"
down_revision = "0005_question_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("trust_provenance", sa.String(32), nullable=True))
    op.add_column("questions", sa.Column("trust_scope_key", sa.String(64), nullable=True))
    op.add_column("questions", sa.Column("trust_sequence", sa.Integer(), nullable=True))
    op.add_column("questions", sa.Column("trust_snapshot_json", sa.Text(), nullable=True))
    op.create_table(
        "judge_trust_counters",
        sa.Column("scope_key", sa.String(64), primary_key=True),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("judge_trust_counters")
    for column in ("trust_snapshot_json", "trust_sequence", "trust_scope_key", "trust_provenance"):
        op.drop_column("questions", column)
