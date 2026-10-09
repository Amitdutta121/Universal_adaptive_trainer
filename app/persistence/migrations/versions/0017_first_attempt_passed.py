"""How many targets of a round passed on their first attempt (ADR-063, m6).

``NULL`` for rounds generated before the count existed: their first attempts were not counted.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_first_attempt_passed"
down_revision = "0016_memory_guidelines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generation_rounds", sa.Column("first_attempt_passed", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("generation_rounds") as batch:
        batch.drop_column("first_attempt_passed")
