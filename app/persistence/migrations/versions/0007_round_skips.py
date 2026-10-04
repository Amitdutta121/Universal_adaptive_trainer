"""Record hard targets a lesson cannot support, separate from drops."""

import sqlalchemy as sa
from alembic import op

revision = "0007_round_skips"
down_revision = "0006_judge_trust"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generation_rounds",
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("generation_rounds", sa.Column("skip_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("generation_rounds", "skip_reason")
    op.drop_column("generation_rounds", "skipped")
