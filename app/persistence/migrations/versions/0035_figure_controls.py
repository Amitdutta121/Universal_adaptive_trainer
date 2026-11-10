"""Professor controls for figures (ADR-080): a course switch, and figure edits in review."""

import sqlalchemy as sa
from alembic import op

revision = "0035_figure_controls"
down_revision = "0034_question_variants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("courses") as batch:
        batch.add_column(
            sa.Column("figures_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("original_figure_json", sa.Text(), nullable=True))
    with op.batch_alter_table("professor_reviews") as batch:
        batch.add_column(sa.Column("edited_figure_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("professor_reviews") as batch:
        batch.drop_column("edited_figure_json")
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("original_figure_json")
    with op.batch_alter_table("courses") as batch:
        batch.drop_column("figures_enabled")
