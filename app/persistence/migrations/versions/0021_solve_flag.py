"""What the blind solvers said against a kept round question's key (app/generation/solve.py)."""

import sqlalchemy as sa
from alembic import op

revision = "0021_solve_flag"
down_revision = "0020_judge_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("solve_flag", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("solve_flag")
