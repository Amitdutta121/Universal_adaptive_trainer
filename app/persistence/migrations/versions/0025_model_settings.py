"""Per-role model settings that override ``.env`` (Task 41)."""

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "0025_model_settings"
down_revision = "0024_evidence_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_settings",
        sa.Column("role", sa.String(length=32), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by",
            GUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL", name="fk_model_settings_updated_by_user"),
            nullable=True,
        ),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey(
                "background_jobs.id", ondelete="SET NULL", name="fk_model_settings_job_id_jobs"
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("model_settings")
