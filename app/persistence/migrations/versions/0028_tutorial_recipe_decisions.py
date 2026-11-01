"""A professor's approval of a tutorial recipe per taxonomy (Phase 6, Task 24)."""

import sqlalchemy as sa
from alembic import op

revision = "0028_tutorial_recipe_decisions"
down_revision = "0027_tutorial_blocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutorial_recipe_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "curriculum_version_id",
            sa.Integer(),
            sa.ForeignKey(
                "curriculum_versions.id",
                ondelete="CASCADE",
                name="fk_tutorial_recipe_decisions_curriculum_version_id_curriculum_versions",
            ),
            nullable=False,
        ),
        sa.Column("recipe_id", sa.String(length=100), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "curriculum_version_id", "recipe_id", name="uq_tutorial_recipe_decisions_pair"
        ),
    )
    op.create_index(
        "ix_tutorial_recipe_decisions_curriculum_version_id",
        "tutorial_recipe_decisions",
        ["curriculum_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tutorial_recipe_decisions_curriculum_version_id",
        table_name="tutorial_recipe_decisions",
    )
    op.drop_table("tutorial_recipe_decisions")
