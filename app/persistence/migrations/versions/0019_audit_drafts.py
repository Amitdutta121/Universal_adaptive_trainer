"""Judge-failed drafts kept for an audit sample (ADR-064, m9).

A round stores at most two of these. They wait in the review queue; they are not
usable questions unless the professor disagrees with the judge and approves them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_audit_drafts"
down_revision = "0018_subtopic_facets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.add_column(
            sa.Column("audit", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("audit_metric", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("audit_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("audit_reason")
        batch.drop_column("audit_metric")
        batch.drop_column("audit")
