"""Tutorial recipes made in the experimental recipe builder, per course."""

import sqlalchemy as sa
from alembic import op

revision = "0031_experimental_recipes"
down_revision = "0030_youtube_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experimental_recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey(
                "courses.id", ondelete="CASCADE", name="fk_experimental_recipes_course_id_courses"
            ),
            nullable=False,
        ),
        sa.Column("recipe_id", sa.String(length=100), nullable=False),
        sa.Column("yaml", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "course_id", "recipe_id", name="uq_experimental_recipes_course_id_recipe_id"
        ),
    )
    op.create_index("ix_experimental_recipes_course_id", "experimental_recipes", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_experimental_recipes_course_id", table_name="experimental_recipes")
    op.drop_table("experimental_recipes")
