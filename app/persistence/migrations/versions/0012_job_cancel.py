"""A background job or question round can be asked to stop: when the professor asked."""

import sqlalchemy as sa
from alembic import op

revision = "0012_job_cancel"
down_revision = "0011_background_jobs"
branch_labels = None
depends_on = None

TABLES = ("background_jobs", "generation_rounds")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table, sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("cancel_requested_at")
