"""Per-course access: ownerless courses get an owner, and batch runs name their course.

Access to a course is now checked against ``courses.owner_id`` (ADR-058), so a course
with no owner would be unreachable. Each one goes to the first user by email, the same
rule ``0002_courses`` used for the default course; with no user yet they stay ownerless.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_course_access"
down_revision = "0008_live_questions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    owner = bind.execute(sa.text('SELECT id FROM "user" ORDER BY email LIMIT 1')).scalar()
    if owner is not None:
        bind.execute(
            sa.text("UPDATE courses SET owner_id = :owner WHERE owner_id IS NULL"),
            {"owner": owner},
        )

    with op.batch_alter_table("judge_batch_runs") as batch:
        batch.add_column(sa.Column("course_id", sa.Integer(), nullable=True))
        batch.create_index("ix_judge_batch_runs_course_id", ["course_id"])
        batch.create_foreign_key("fk_judge_batch_runs_course_id", "courses", ["course_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("judge_batch_runs") as batch:
        batch.drop_constraint("fk_judge_batch_runs_course_id", type_="foreignkey")
        batch.drop_index("ix_judge_batch_runs_course_id")
        batch.drop_column("course_id")
