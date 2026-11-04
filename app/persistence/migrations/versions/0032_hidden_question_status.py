"""``QuestionStatus.HIDDEN``: approved questions hidden from students (ADR-070, task-139).

``questions.status`` is a plain ``VARCHAR(32)`` (``StrEnumType``) with no CHECK constraint or
native enum, so the new value needs no schema change on SQLite or Postgres. The revision exists
so the value has a recorded starting point and a safe way back: a downgrade turns every hidden
question back into an approved one, since code before this revision cannot read ``hidden``.
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_hidden_question_status"
down_revision = "0031_experimental_recipes"
branch_labels = None
depends_on = None

_questions = sa.table("questions", sa.column("status", sa.String(32)))


def upgrade() -> None:
    """Nothing to change: the column already accepts any status string."""


def downgrade() -> None:
    op.execute(_questions.update().where(_questions.c.status == "hidden").values(status="approved"))
