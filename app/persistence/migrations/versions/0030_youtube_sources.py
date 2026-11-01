"""YouTube sources: a book row's video id and embed availability (Phase 7, Task 30)."""

import sqlalchemy as sa
from alembic import op

revision = "0030_youtube_sources"
down_revision = "0029_tutorial_block_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("books") as batch:
        batch.add_column(sa.Column("video_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("video_availability", sa.String(length=16), nullable=True))
        batch.add_column(
            sa.Column("availability_checked_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("books") as batch:
        batch.drop_column("availability_checked_at")
        batch.drop_column("video_availability")
        batch.drop_column("video_id")
