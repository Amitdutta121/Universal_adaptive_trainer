"""Computed-figure copies of a question, and the copy an attempt was served (ADR-080)."""

import sqlalchemy as sa
from alembic import op

revision = "0034_question_variants"
down_revision = "0033_agent_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey(
                "questions.id",
                ondelete="CASCADE",
                name="fk_question_variants_question_id_questions",
            ),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey(
                "courses.id", ondelete="CASCADE", name="fk_question_variants_course_id_courses"
            ),
            nullable=False,
        ),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("reference_solution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("question_id", "ordinal", name="uq_question_variants_question_ordinal"),
    )
    op.create_index("ix_question_variants_question_id", "question_variants", ["question_id"])
    op.create_index("ix_question_variants_course_id", "question_variants", ["course_id"])
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("figure_program", sa.Text(), nullable=True))
    with op.batch_alter_table("student_attempts") as batch:
        batch.add_column(sa.Column("variant_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_student_attempts_variant_id_question_variants",
            "question_variants",
            ["variant_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("student_attempts") as batch:
        batch.drop_constraint(
            "fk_student_attempts_variant_id_question_variants", type_="foreignkey"
        )
        batch.drop_column("variant_id")
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("figure_program")
    op.drop_index("ix_question_variants_course_id", table_name="question_variants")
    op.drop_index("ix_question_variants_question_id", table_name="question_variants")
    op.drop_table("question_variants")
