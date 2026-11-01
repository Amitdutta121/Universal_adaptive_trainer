"""Judge-prompt overrides and learned type instructions are scoped per subject.

A rule learned in a Python course must never reach a Physics course, so both tables gain a
``subject`` column and their uniqueness moves from one row per metric / question type to one
row per (subject, metric) / (subject, question type). Every row that exists already was
learned or edited for Intro Python, so it becomes ``intro_python``.

Revision ID: 0004_subject_scoped_personalization
Revises: 0003_course_question_types
Create Date: 2026-10-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_subject_scoped_personalization"
down_revision = "0003_course_question_types"
branch_labels = None
depends_on = None

#: Frozen here, not imported: a migration must keep meaning what it meant when it was written.
LEGACY_SUBJECT = "intro_python"

#: (table, key column, unique constraint added by this revision)
TABLES = (
    ("judge_prompts", "metric", "uq_judge_prompts_subject_metric"),
    ("type_instructions", "question_type", "uq_type_instructions_subject_type"),
)


def upgrade() -> None:
    bind = op.get_bind()
    for table, key, constraint in TABLES:
        # The single-column index was the uniqueness rule; it stays, non-unique, for lookups.
        op.drop_index(f"ix_{table}_{key}", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "subject",
                    sa.String(50),
                    nullable=False,
                    server_default=LEGACY_SUBJECT,
                )
            )
            batch.create_unique_constraint(constraint, ["subject", key])
        bind.execute(
            sa.text(f"UPDATE {table} SET subject = :subject WHERE subject IS NULL"),
            {"subject": LEGACY_SUBJECT},
        )
        op.create_index(f"ix_{table}_{key}", table, [key], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table, key, constraint in TABLES:
        # The old schema holds one row per key, which only the legacy subject's rows fit.
        bind.execute(
            sa.text(f"DELETE FROM {table} WHERE subject != :subject"),
            {"subject": LEGACY_SUBJECT},
        )
        op.drop_index(f"ix_{table}_{key}", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="unique")
            batch.drop_column("subject")
        op.create_index(f"ix_{table}_{key}", table, [key], unique=True)
