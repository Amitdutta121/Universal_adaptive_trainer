"""Facets per subtopic, listed once and reused by rounds; saturated cells on the round (m7)."""

import sqlalchemy as sa
from alembic import op

revision = "0018_subtopic_facets"
down_revision = "0017_first_attempt_passed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subtopic_facets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subtopic_id",
            sa.Integer(),
            sa.ForeignKey("subtopics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("facets_json", sa.Text(), nullable=False),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_subtopic_facets_subtopic_id", "subtopic_facets", ["subtopic_id"], unique=True
    )
    op.add_column("generation_rounds", sa.Column("saturated", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_rounds") as batch:
        batch.drop_column("saturated")
    op.drop_index("ix_subtopic_facets_subtopic_id", table_name="subtopic_facets")
    op.drop_table("subtopic_facets")
