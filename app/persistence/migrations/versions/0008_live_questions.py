"""Questions generated on demand for a student who had nothing left to answer."""

import sqlalchemy as sa
from alembic import op

revision = "0008_live_questions"
down_revision = "0007_round_skips"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("live_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "live_question_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "training_session_id",
            sa.Integer(),
            sa.ForeignKey("training_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "setup_id",
            sa.Integer(),
            sa.ForeignKey("question_setups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "subtopic_id",
            sa.Integer(),
            sa.ForeignKey("subtopics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_difficulty", sa.String(16), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("style_id", sa.String(100), nullable=True),
        sa.Column("mastery", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey("student_attempts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_live_question_jobs_training_session_id",
        "live_question_jobs",
        ["training_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_live_question_jobs_training_session_id", "live_question_jobs")
    op.drop_table("live_question_jobs")
    op.drop_column("questions", "live_generated")
