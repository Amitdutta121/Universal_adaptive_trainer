"""Question setup: setups, generation rounds, custom rule judges, and the columns they need.

Three new tables (``question_setups``, ``generation_rounds``, ``custom_judges``) and nullable
columns on existing ones: which style, round and target subtopic produced a question; the
professor's difficulty and subtopic corrections on a review; and custom-judge results on an
evaluation. Every new column is nullable or defaulted, so existing rows need no backfill --
``NULL`` reads as "not produced by a setup round" / "no correction given".

Revision ID: 0005_question_setup
Revises: 0004_subject_scoped_personalization
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_question_setup"
down_revision = "0004_subject_scoped_personalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_setups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "curriculum_version_id",
            sa.Integer(),
            sa.ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("approved_styles_json", sa.Text(), nullable=True),
        sa.Column("cell_targets_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_question_setups_curriculum_version_id", "question_setups", ["curriculum_version_id"]
    )

    op.create_table(
        "generation_rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "setup_id",
            sa.Integer(),
            sa.ForeignKey("question_setups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("targets_json", sa.Text(), nullable=True),
        sa.Column("requested", sa.Integer(), nullable=False),
        sa.Column("produced", sa.Integer(), nullable=False),
        sa.Column("dropped", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("setup_id", "number", name="uq_generation_rounds_setup_number"),
    )
    op.create_index("ix_generation_rounds_setup_id", "generation_rounds", ["setup_id"])

    op.create_table(
        "custom_judges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "curriculum_version_id",
            sa.Integer(),
            sa.ForeignKey("curriculum_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_custom_judges_curriculum_version_id", "custom_judges", ["curriculum_version_id"]
    )

    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("style_id", sa.String(100), nullable=True))
        batch.add_column(sa.Column("round_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("target_subtopic_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_questions_round_id",
            "generation_rounds",
            ["round_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_questions_target_subtopic_id",
            "subtopics",
            ["target_subtopic_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_questions_style_id", ["style_id"])
        batch.create_index("ix_questions_round_id", ["round_id"])

    with op.batch_alter_table("professor_reviews") as batch:
        batch.add_column(sa.Column("corrected_difficulty", sa.String(16), nullable=True))
        batch.add_column(sa.Column("corrected_subtopic_ids_json", sa.Text(), nullable=True))

    with op.batch_alter_table("question_evaluations") as batch:
        batch.add_column(sa.Column("custom_results_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("question_evaluations") as batch:
        batch.drop_column("custom_results_json")

    with op.batch_alter_table("professor_reviews") as batch:
        batch.drop_column("corrected_subtopic_ids_json")
        batch.drop_column("corrected_difficulty")

    with op.batch_alter_table("questions") as batch:
        # No drop_constraint: the foreign keys are unnamed when ``create_all`` built the
        # table, and the batch rebuild drops them with their columns (as in 0002).
        batch.drop_index("ix_questions_round_id")
        batch.drop_index("ix_questions_style_id")
        batch.drop_column("target_subtopic_id")
        batch.drop_column("round_id")
        batch.drop_column("style_id")

    op.drop_index("ix_custom_judges_curriculum_version_id", "custom_judges")
    op.drop_table("custom_judges")
    op.drop_index("ix_generation_rounds_setup_id", "generation_rounds")
    op.drop_table("generation_rounds")
    op.drop_index("ix_question_setups_curriculum_version_id", "question_setups")
    op.drop_table("question_setups")
