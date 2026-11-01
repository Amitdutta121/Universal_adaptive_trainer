"""Baseline: the schema ``create_all`` built before migrations existed.

Rendered by Alembic autogenerate from the models at commit d5c0fa4 (the last
commit before migrations), with the app's TypeDecorators written as their
underlying column types so this file never changes when the models do. A
database that predates Alembic is stamped here by ``init_db`` instead of
running it.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-01
"""

from __future__ import annotations

import fastapi_users_db_sqlalchemy.generics
import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("stored_filename", sa.String(length=500), nullable=True),
        sa.Column("source_format", sa.String(length=16), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_filename", sa.String(length=500), nullable=True),
        sa.Column("producer", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "curriculum_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_book_ids_json", sa.Text(), nullable=True),
        sa.Column("generated_by", sa.String(length=200), nullable=True),
        sa.Column("extraction_metadata_json", sa.Text(), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "judge_batch_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("provider_batch_ids_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("rubric_version", sa.String(length=50), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_judge_batch_runs_run_id"), "judge_batch_runs", ["run_id"], unique=True)
    op.create_table(
        "judge_prompts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("rules_json", sa.Text(), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("learned", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_judge_prompts_metric"), "judge_prompts", ["metric"], unique=True)
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("resume_token", sa.String(length=43), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_students_display_name"), "students", ["display_name"], unique=True)
    op.create_index(op.f("ix_students_resume_token"), "students", ["resume_token"], unique=True)
    op.create_table(
        "type_instructions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(length=32), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("rules_json", sa.Text(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_type_instructions_question_type"),
        "type_instructions",
        ["question_type"],
        unique=True,
    )
    op.create_table(
        "user",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)
    op.create_table(
        "accesstoken",
        sa.Column("user_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("token", sa.String(length=43), nullable=False),
        sa.Column(
            "created_at",
            fastapi_users_db_sqlalchemy.generics.TIMESTAMPAware(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index(op.f("ix_accesstoken_created_at"), "accesstoken", ["created_at"], unique=False)
    op.create_table(
        "book_chapters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=True),
        sa.Column("end_page", sa.Integer(), nullable=True),
        sa.Column("structure_source", sa.String(length=32), nullable=False),
        sa.Column("structure_confidence", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_book_chapters_book_id"), "book_chapters", ["book_id"], unique=False)
    op.create_table(
        "question_set_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("curriculum_version_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"], ["curriculum_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("curriculum_version_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=True),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"], ["curriculum_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_topics_stable_id"), "topics", ["stable_id"], unique=False)
    op.create_table(
        "book_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=True),
        sa.Column("end_page", sa.Integer(), nullable=True),
        sa.Column("structure_source", sa.String(length=32), nullable=False),
        sa.Column("structure_confidence", sa.String(length=16), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["book_chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_book_sections_book_id"), "book_sections", ["book_id"], unique=False)
    op.create_index(
        op.f("ix_book_sections_chapter_id"), "book_sections", ["chapter_id"], unique=False
    )
    op.create_table(
        "question_set_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=50), nullable=False),
        sa.Column("set_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["set_version_id"], ["question_set_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_question_set_aliases_alias"), "question_set_aliases", ["alias"], unique=True
    )
    op.create_index(
        op.f("ix_question_set_aliases_set_version_id"),
        "question_set_aliases",
        ["set_version_id"],
        unique=False,
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("curriculum_version_id", sa.Integer(), nullable=True),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("question_type", sa.String(length=32), nullable=True),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("reference_solution", sa.Text(), nullable=True),
        sa.Column("tests", sa.Text(), nullable=True),
        sa.Column("spec_json", sa.Text(), nullable=True),
        sa.Column("content_json", sa.Text(), nullable=True),
        sa.Column("validation_report_json", sa.Text(), nullable=True),
        sa.Column("generation_attempts_json", sa.Text(), nullable=True),
        sa.Column("pedagogical_eval_json", sa.Text(), nullable=True),
        sa.Column("original_prompt", sa.Text(), nullable=True),
        sa.Column("original_reference_solution", sa.Text(), nullable=True),
        sa.Column("original_tests", sa.Text(), nullable=True),
        sa.Column("regenerated_from_question_id", sa.Integer(), nullable=True),
        sa.Column("regeneration_feedback", sa.Text(), nullable=True),
        sa.Column("generator_kind", sa.String(length=32), nullable=False),
        sa.Column("generator_name", sa.String(length=200), nullable=False),
        sa.Column("generator_version", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("times_used", sa.Integer(), nullable=False),
        sa.Column("personalization_context_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"], ["curriculum_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["regenerated_from_question_id"], ["questions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_questions_regenerated_from_question_id"),
        "questions",
        ["regenerated_from_question_id"],
        unique=False,
    )
    op.create_table(
        "student_topic_mastery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("p_known", sa.Float(), nullable=False),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "topic_id", name="uq_student_topic_mastery_pair"),
    )
    op.create_index(
        op.f("ix_student_topic_mastery_student_id"),
        "student_topic_mastery",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_topic_mastery_topic_id"),
        "student_topic_mastery",
        ["topic_id"],
        unique=False,
    )
    op.create_table(
        "subtopics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=True),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("candidate_labels_json", sa.Text(), nullable=True),
        sa.Column("grouping_reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subtopics_stable_id"), "subtopics", ["stable_id"], unique=False)
    op.create_table(
        "training_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("set_version_id", sa.Integer(), nullable=True),
        sa.Column("rng_seed", sa.Integer(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["set_version_id"], ["question_set_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_training_sessions_set_version_id"),
        "training_sessions",
        ["set_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_training_sessions_student_id"), "training_sessions", ["student_id"], unique=False
    )
    op.create_table(
        "professor_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("edited_prompt", sa.Text(), nullable=True),
        sa.Column("edited_reference_solution", sa.Text(), nullable=True),
        sa.Column("edited_tests", sa.Text(), nullable=True),
        sa.Column("changed_fields_json", sa.Text(), nullable=True),
        sa.Column("professor_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_generator_name", sa.String(length=200), nullable=True),
        sa.Column("reviewed_generator_version", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "question_evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_json", sa.Text(), nullable=True),
        sa.Column("judge_model", sa.String(length=200), nullable=True),
        sa.Column("rubric_version", sa.String(length=50), nullable=True),
        sa.Column("eval_status", sa.String(length=32), nullable=True),
        sa.Column("gate", sa.String(length=32), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "question_id", name="uq_question_evaluations_run_question"),
    )
    op.create_index(
        op.f("ix_question_evaluations_question_id"),
        "question_evaluations",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_evaluations_run_id"), "question_evaluations", ["run_id"], unique=False
    )
    op.create_table(
        "question_set_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("set_version_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["set_version_id"], ["question_set_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("set_version_id", "question_id", name="uq_question_set_members_pair"),
    )
    op.create_index(
        op.f("ix_question_set_members_question_id"),
        "question_set_members",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_set_members_set_version_id"),
        "question_set_members",
        ["set_version_id"],
        unique=False,
    )
    op.create_table(
        "question_similarity_flags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("similar_question_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["similar_question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_question_similarity_flags_question_id"),
        "question_similarity_flags",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_similarity_flags_similar_question_id"),
        "question_similarity_flags",
        ["similar_question_id"],
        unique=False,
    )
    op.create_table(
        "question_subtopics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("subtopic_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "subtopic_id", name="uq_question_subtopics_pair"),
    )
    op.create_index(
        op.f("ix_question_subtopics_question_id"),
        "question_subtopics",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_subtopics_subtopic_id"),
        "question_subtopics",
        ["subtopic_id"],
        unique=False,
    )
    op.create_table(
        "section_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["section_id"], ["book_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_section_embeddings_section_id"), "section_embeddings", ["section_id"], unique=True
    )
    op.create_table(
        "student_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("subtopic_id", sa.Integer(), nullable=True),
        sa.Column("requested_difficulty", sa.String(length=16), nullable=False),
        sa.Column("served_difficulty", sa.String(length=16), nullable=False),
        sa.Column("mastery_before", sa.Float(), nullable=True),
        sa.Column("mastery_after", sa.Float(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("passed_tests", sa.Integer(), nullable=True),
        sa.Column("total_tests", sa.Integer(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["training_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "ordinal", name="uq_student_attempts_session_ordinal"),
    )
    op.create_index(
        op.f("ix_student_attempts_question_id"), "student_attempts", ["question_id"], unique=False
    )
    op.create_index(
        op.f("ix_student_attempts_session_id"), "student_attempts", ["session_id"], unique=False
    )
    op.create_index(
        op.f("ix_student_attempts_student_id"), "student_attempts", ["student_id"], unique=False
    )
    op.create_index(
        op.f("ix_student_attempts_subtopic_id"), "student_attempts", ["subtopic_id"], unique=False
    )
    op.create_table(
        "student_subtopic_weakness",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("subtopic_id", sa.Integer(), nullable=False),
        sa.Column("weakness", sa.Float(), nullable=False),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "subtopic_id", name="uq_student_subtopic_weakness_pair"),
    )
    op.create_index(
        op.f("ix_student_subtopic_weakness_student_id"),
        "student_subtopic_weakness",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_subtopic_weakness_subtopic_id"),
        "student_subtopic_weakness",
        ["subtopic_id"],
        unique=False,
    )
    op.create_table(
        "subtopic_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subtopic_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("candidate_label", sa.String(length=300), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("quotes_json", sa.Text(), nullable=True),
        sa.Column("citation", sa.String(length=1000), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["book_sections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subtopic_id"], ["subtopics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subtopic_evidence_book_id"), "subtopic_evidence", ["book_id"], unique=False
    )
    op.create_index(
        op.f("ix_subtopic_evidence_section_id"), "subtopic_evidence", ["section_id"], unique=False
    )
    op.create_index(
        op.f("ix_subtopic_evidence_subtopic_id"), "subtopic_evidence", ["subtopic_id"], unique=False
    )
    op.create_table(
        "review_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(length=32), nullable=True),
        sa.Column("cell", sa.String(length=32), nullable=False),
        sa.Column("judge", sa.String(length=16), nullable=False),
        sa.Column("professor", sa.String(length=16), nullable=False),
        sa.Column("rubric_version", sa.String(length=50), nullable=True),
        sa.Column("judge_model", sa.String(length=200), nullable=True),
        sa.Column("attributed_metrics_json", sa.Text(), nullable=True),
        sa.Column("held_out", sa.Boolean(), nullable=False),
        sa.Column("judge_rationales_json", sa.Text(), nullable=True),
        sa.Column("instruction_refreshed", sa.Boolean(), nullable=False),
        sa.Column("refresh_error", sa.Text(), nullable=True),
        sa.Column("judges_refreshed_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["professor_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_outcomes_cell"), "review_outcomes", ["cell"], unique=False)
    op.create_index(
        op.f("ix_review_outcomes_question_id"), "review_outcomes", ["question_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_outcomes_question_type"), "review_outcomes", ["question_type"], unique=False
    )
    op.create_index(
        op.f("ix_review_outcomes_review_id"), "review_outcomes", ["review_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_review_outcomes_review_id"), table_name="review_outcomes")
    op.drop_index(op.f("ix_review_outcomes_question_type"), table_name="review_outcomes")
    op.drop_index(op.f("ix_review_outcomes_question_id"), table_name="review_outcomes")
    op.drop_index(op.f("ix_review_outcomes_cell"), table_name="review_outcomes")
    op.drop_table("review_outcomes")
    op.drop_index(op.f("ix_subtopic_evidence_subtopic_id"), table_name="subtopic_evidence")
    op.drop_index(op.f("ix_subtopic_evidence_section_id"), table_name="subtopic_evidence")
    op.drop_index(op.f("ix_subtopic_evidence_book_id"), table_name="subtopic_evidence")
    op.drop_table("subtopic_evidence")
    op.drop_index(
        op.f("ix_student_subtopic_weakness_subtopic_id"), table_name="student_subtopic_weakness"
    )
    op.drop_index(
        op.f("ix_student_subtopic_weakness_student_id"), table_name="student_subtopic_weakness"
    )
    op.drop_table("student_subtopic_weakness")
    op.drop_index(op.f("ix_student_attempts_subtopic_id"), table_name="student_attempts")
    op.drop_index(op.f("ix_student_attempts_student_id"), table_name="student_attempts")
    op.drop_index(op.f("ix_student_attempts_session_id"), table_name="student_attempts")
    op.drop_index(op.f("ix_student_attempts_question_id"), table_name="student_attempts")
    op.drop_table("student_attempts")
    op.drop_index(op.f("ix_section_embeddings_section_id"), table_name="section_embeddings")
    op.drop_table("section_embeddings")
    op.drop_index(op.f("ix_question_subtopics_subtopic_id"), table_name="question_subtopics")
    op.drop_index(op.f("ix_question_subtopics_question_id"), table_name="question_subtopics")
    op.drop_table("question_subtopics")
    op.drop_index(
        op.f("ix_question_similarity_flags_similar_question_id"),
        table_name="question_similarity_flags",
    )
    op.drop_index(
        op.f("ix_question_similarity_flags_question_id"), table_name="question_similarity_flags"
    )
    op.drop_table("question_similarity_flags")
    op.drop_index(op.f("ix_question_set_members_set_version_id"), table_name="question_set_members")
    op.drop_index(op.f("ix_question_set_members_question_id"), table_name="question_set_members")
    op.drop_table("question_set_members")
    op.drop_index(op.f("ix_question_evaluations_run_id"), table_name="question_evaluations")
    op.drop_index(op.f("ix_question_evaluations_question_id"), table_name="question_evaluations")
    op.drop_table("question_evaluations")
    op.drop_table("professor_reviews")
    op.drop_index(op.f("ix_training_sessions_student_id"), table_name="training_sessions")
    op.drop_index(op.f("ix_training_sessions_set_version_id"), table_name="training_sessions")
    op.drop_table("training_sessions")
    op.drop_index(op.f("ix_subtopics_stable_id"), table_name="subtopics")
    op.drop_table("subtopics")
    op.drop_index(op.f("ix_student_topic_mastery_topic_id"), table_name="student_topic_mastery")
    op.drop_index(op.f("ix_student_topic_mastery_student_id"), table_name="student_topic_mastery")
    op.drop_table("student_topic_mastery")
    op.drop_index(op.f("ix_questions_regenerated_from_question_id"), table_name="questions")
    op.drop_table("questions")
    op.drop_index(op.f("ix_question_set_aliases_set_version_id"), table_name="question_set_aliases")
    op.drop_index(op.f("ix_question_set_aliases_alias"), table_name="question_set_aliases")
    op.drop_table("question_set_aliases")
    op.drop_index(op.f("ix_book_sections_chapter_id"), table_name="book_sections")
    op.drop_index(op.f("ix_book_sections_book_id"), table_name="book_sections")
    op.drop_table("book_sections")
    op.drop_index(op.f("ix_topics_stable_id"), table_name="topics")
    op.drop_table("topics")
    op.drop_table("question_set_versions")
    op.drop_index(op.f("ix_book_chapters_book_id"), table_name="book_chapters")
    op.drop_table("book_chapters")
    op.drop_index(op.f("ix_accesstoken_created_at"), table_name="accesstoken")
    op.drop_table("accesstoken")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")
    op.drop_index(op.f("ix_type_instructions_question_type"), table_name="type_instructions")
    op.drop_table("type_instructions")
    op.drop_index(op.f("ix_students_resume_token"), table_name="students")
    op.drop_index(op.f("ix_students_display_name"), table_name="students")
    op.drop_table("students")
    op.drop_index(op.f("ix_judge_prompts_metric"), table_name="judge_prompts")
    op.drop_table("judge_prompts")
    op.drop_index(op.f("ix_judge_batch_runs_run_id"), table_name="judge_batch_runs")
    op.drop_table("judge_batch_runs")
    op.drop_table("curriculum_versions")
    op.drop_table("books")
