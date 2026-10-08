"""Reviews are learned once per round (ADR-063): which round learned each, and what it applied.

Existing outcomes were already learned when they were submitted, so they are marked ``0``
rather than left pending; otherwise the first round after the upgrade would relearn every type
and judge from the whole history at once.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_lessons_round"
down_revision = "0012_job_cancel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_outcomes", sa.Column("lessons_round_id", sa.Integer(), nullable=True))
    op.create_index("ix_review_outcomes_lessons_round_id", "review_outcomes", ["lessons_round_id"])
    op.execute("UPDATE review_outcomes SET lessons_round_id = 0")
    op.add_column(
        "generation_rounds",
        sa.Column("lessons_applied", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("generation_rounds", sa.Column("lessons_error", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_rounds") as batch:
        batch.drop_column("lessons_error")
        batch.drop_column("lessons_applied")
    with op.batch_alter_table("review_outcomes") as batch:
        batch.drop_index("ix_review_outcomes_lessons_round_id")
        batch.drop_column("lessons_round_id")
