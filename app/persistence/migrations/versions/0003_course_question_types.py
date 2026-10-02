"""Courses record their subject, chosen question types and derived capabilities (ADR-054).

Every course that exists already was built for Intro Python, so it gets that subject and all
seven question types the application could generate before this change -- nothing it could do
before is taken away.

Revision ID: 0003_course_question_types
Revises: 0002_courses
Create Date: 2026-10-02
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0003_course_question_types"
down_revision = "0002_courses"
branch_labels = None
depends_on = None

#: Frozen here, not imported: a migration must keep meaning what it meant when it was written.
LEGACY_SUBJECT = "intro_python"
LEGACY_TYPES = [
    "multiple_choice",
    "true_false",
    "parsons",
    "output_prediction",
    "code_completion",
    "debugging",
    "coding",
]
LEGACY_CAPABILITIES = [
    "structured.choice",
    "structured.ordering",
    "text.normalized_match",
    "code.python.execute",
    "code.python.tests",
]


def upgrade() -> None:
    with op.batch_alter_table("courses") as batch:
        batch.add_column(sa.Column("subject", sa.String(50), nullable=True))
        batch.add_column(sa.Column("question_types_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("capabilities_json", sa.Text(), nullable=True))
    op.get_bind().execute(
        sa.text(
            "UPDATE courses SET subject = :subject, question_types_json = :types, "
            "capabilities_json = :caps"
        ),
        {
            "subject": LEGACY_SUBJECT,
            "types": json.dumps(LEGACY_TYPES),
            "caps": json.dumps(LEGACY_CAPABILITIES),
        },
    )


def downgrade() -> None:
    with op.batch_alter_table("courses") as batch:
        batch.drop_column("capabilities_json")
        batch.drop_column("question_types_json")
        batch.drop_column("subject")
