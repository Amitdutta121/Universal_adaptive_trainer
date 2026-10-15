"""Course-local question styles (Task 18)."""

import sqlalchemy as sa
from alembic import op

revision = "0026_course_styles"
down_revision = "0025_model_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_styles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey(
                "courses.id", ondelete="CASCADE", name="fk_course_styles_course_id_courses"
            ),
            nullable=False,
        ),
        sa.Column("style_id", sa.String(length=100), nullable=False),
        sa.Column("style_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("course_id", "style_id", name="uq_course_styles_course_id_style_id"),
    )
    op.create_index("ix_course_styles_course_id", "course_styles", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_course_styles_course_id", table_name="course_styles")
    op.drop_table("course_styles")
