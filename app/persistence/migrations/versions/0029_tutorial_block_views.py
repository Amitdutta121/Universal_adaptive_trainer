"""Tutorial blocks shown to students and the next answer's outcome (Phase 6, Task 28)."""

import sqlalchemy as sa
from alembic import op

revision = "0029_tutorial_block_views"
down_revision = "0028_tutorial_recipe_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutorial_block_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey(
                "student_attempts.id",
                ondelete="CASCADE",
                name="fk_tutorial_block_views_attempt_id_student_attempts",
            ),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey(
                "training_sessions.id",
                ondelete="CASCADE",
                name="fk_tutorial_block_views_session_id_training_sessions",
            ),
            nullable=False,
        ),
        sa.Column(
            "block_id",
            sa.Integer(),
            sa.ForeignKey(
                "tutorial_blocks.id",
                ondelete="CASCADE",
                name="fk_tutorial_block_views_block_id_tutorial_blocks",
            ),
            nullable=False,
        ),
        sa.Column("recipe_id", sa.String(length=100), nullable=False),
        sa.Column("subtopic_id", sa.Integer(), nullable=False),
        sa.Column("moment", sa.String(length=8), nullable=False),
        sa.Column("next_correct", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "attempt_id", "block_id", "moment", name="uq_tutorial_block_views_shown"
        ),
    )
    op.create_index("ix_tutorial_block_views_attempt_id", "tutorial_block_views", ["attempt_id"])
    op.create_index("ix_tutorial_block_views_session_id", "tutorial_block_views", ["session_id"])
    op.create_index("ix_tutorial_block_views_recipe_id", "tutorial_block_views", ["recipe_id"])


def downgrade() -> None:
    op.drop_index("ix_tutorial_block_views_recipe_id", table_name="tutorial_block_views")
    op.drop_index("ix_tutorial_block_views_session_id", table_name="tutorial_block_views")
    op.drop_index("ix_tutorial_block_views_attempt_id", table_name="tutorial_block_views")
    op.drop_table("tutorial_block_views")
