"""Generated tutorial blocks (Phase 5, Task 19)."""

import sqlalchemy as sa
from alembic import op

revision = "0027_tutorial_blocks"
down_revision = "0026_course_styles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutorial_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subtopic_id",
            sa.Integer(),
            sa.ForeignKey(
                "subtopics.id", ondelete="CASCADE", name="fk_tutorial_blocks_subtopic_id_subtopics"
            ),
            nullable=False,
        ),
        sa.Column("recipe_id", sa.String(length=100), nullable=False),
        sa.Column("guidance_level", sa.String(length=16), nullable=False),
        sa.Column("renderer", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("chunk_ids_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column(
            "set_version_id",
            sa.Integer(),
            sa.ForeignKey(
                "question_set_versions.id",
                ondelete="SET NULL",
                name="fk_tutorial_blocks_set_version_id_question_set_versions",
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("chunk_ids_json <> '[]'", name="ck_tutorial_blocks_chunk_ids"),
    )
    op.create_index("ix_tutorial_blocks_subtopic_id", "tutorial_blocks", ["subtopic_id"])
    op.create_index("ix_tutorial_blocks_recipe_id", "tutorial_blocks", ["recipe_id"])
    op.create_index("ix_tutorial_blocks_set_version_id", "tutorial_blocks", ["set_version_id"])


def downgrade() -> None:
    op.drop_index("ix_tutorial_blocks_set_version_id", table_name="tutorial_blocks")
    op.drop_index("ix_tutorial_blocks_recipe_id", table_name="tutorial_blocks")
    op.drop_index("ix_tutorial_blocks_subtopic_id", table_name="tutorial_blocks")
    op.drop_table("tutorial_blocks")
