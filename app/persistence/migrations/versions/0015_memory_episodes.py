"""Memory episodes: one per professor review (ADR-063 point 3, ADR-064).

Every existing review is back-filled as an episode, rebuilt from what the database still
holds: the text as it stood at that review (an edit's ``edited_prompt``, else the prompt in
force then), the classification the question had before any correction (``spec_json`` keeps
it when one was made), the course's personal subject key, and the judges' verdicts from the
newest evaluation recorded at or before the review (else the question's current one).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0015_memory_episodes"
down_revision = "0014_question_embeddings"
branch_labels = None
depends_on = None

#: Frozen here, not imported: a migration must keep meaning what it meant when it was written.
LEGACY_SUBJECT = "intro_python"
PRESET_SUBJECTS = {"intro_python", "physics", "ml_llms", "biology"}
VERDICT_FIELDS = (
    "status",
    "passed",
    "rationale",
    "issue_codes",
    "proposed_difficulty",
    "proposed_subtopic_ids",
)


def upgrade() -> None:
    op.create_table(
        "memory_episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=True),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=100), nullable=False),
        sa.Column("question_type", sa.String(length=32), nullable=True),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("subtopic_ids_json", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("corrected_difficulty", sa.String(length=16), nullable=True),
        sa.Column("corrected_subtopic_ids_json", sa.Text(), nullable=True),
        sa.Column("judge_verdicts_json", sa.Text(), nullable=True),
        sa.Column("rubric_version", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["professor_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memory_episodes_review_id"), "memory_episodes", ["review_id"], unique=True
    )
    op.create_index(op.f("ix_memory_episodes_question_id"), "memory_episodes", ["question_id"])
    op.create_index(op.f("ix_memory_episodes_subject"), "memory_episodes", ["subject"])
    op.create_index(op.f("ix_memory_episodes_question_type"), "memory_episodes", ["question_type"])
    _backfill(op.get_bind())


def downgrade() -> None:
    op.drop_index(op.f("ix_memory_episodes_question_type"), table_name="memory_episodes")
    op.drop_index(op.f("ix_memory_episodes_subject"), table_name="memory_episodes")
    op.drop_index(op.f("ix_memory_episodes_question_id"), table_name="memory_episodes")
    op.drop_index(op.f("ix_memory_episodes_review_id"), table_name="memory_episodes")
    op.drop_table("memory_episodes")


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return decoded if isinstance(decoded, type(default)) else default


def _embed_text(prompt: str | None, content: dict) -> str:
    """Prompt, code, options: ``app.retrieval.duplicates.embed_text`` as of this revision."""
    parts = [prompt or ""]
    if content.get("code"):
        parts.append(str(content["code"]))
    options = content.get("options")
    if isinstance(options, list):
        parts.extend(str(option) for option in options)
    return "\n".join(parts)


def _personal_key(course: Any) -> str:
    """``SubjectProfile.personal_key`` as of this revision; no course is Intro Python."""
    if course is None:
        return LEGACY_SUBJECT
    subject = course.subject or LEGACY_SUBJECT
    if subject not in PRESET_SUBJECTS:
        return f"custom:{course.id}"
    if course.owner_id is None:
        return subject
    return f"{subject}@{uuid.UUID(str(course.owner_id)).hex}"


def _verdicts(evaluation: dict) -> dict:
    verdicts = {}
    for metric in evaluation.get("metrics") or []:
        if isinstance(metric, dict) and metric.get("metric"):
            verdicts[str(metric["metric"])] = {key: metric.get(key) for key in VERDICT_FIELDS}
    return verdicts


def _backfill(bind: sa.Connection) -> None:
    courses = {
        row.version_id: row
        for row in bind.execute(
            sa.text(
                "SELECT v.id AS version_id, c.id, c.subject, c.owner_id FROM curriculum_versions v "
                "JOIN courses c ON c.id = v.course_id"
            )
        )
    }
    questions = {
        row.id: row
        for row in bind.execute(
            sa.text(
                "SELECT id, curriculum_version_id, question_type, difficulty, topic_id, prompt, "
                "original_prompt, content_json, spec_json, pedagogical_eval_json FROM questions"
            )
        )
    }
    links: dict[int, list[int]] = {}
    for row in bind.execute(
        sa.text("SELECT question_id, subtopic_id FROM question_subtopics ORDER BY id")
    ):
        links.setdefault(row.question_id, []).append(row.subtopic_id)
    reviews = list(
        bind.execute(
            sa.text(
                "SELECT id, question_id, decision, reasons_json, comment, edited_prompt, "
                "corrected_difficulty, corrected_subtopic_ids_json, created_at "
                "FROM professor_reviews ORDER BY question_id, id"
            )
        )
    )
    edited_questions = {row.question_id for row in reviews if row.decision == "edit"}

    episodes = []
    current_text: dict[int, str | None] = {}
    for review in reviews:
        question = questions.get(review.question_id)
        if question is None:
            continue
        content = _json(question.content_json, {})
        spec = _json(question.spec_json, {})
        if review.question_id not in current_text:
            # Before any edit the prompt was the generated one.
            first = question.original_prompt if review.question_id in edited_questions else None
            current_text[review.question_id] = first or question.prompt
        reviewed = _embed_text(current_text[review.question_id], content)
        edited = review.decision == "edit"
        if edited and review.edited_prompt is not None:
            current_text[review.question_id] = review.edited_prompt
        evaluation = bind.execute(
            sa.text(
                "SELECT evaluation_json FROM question_evaluations WHERE question_id = :q "
                "AND created_at <= :at ORDER BY created_at DESC, id DESC LIMIT 1"
            ),
            {"q": question.id, "at": review.created_at},
        ).scalar()
        blob = _json(evaluation, {}) or _json(question.pedagogical_eval_json, {})
        subtopic_ids = spec.get("subtopic_ids", links.get(question.id, []))
        episodes.append(
            {
                "review_id": review.id,
                "question_id": question.id,
                "source": "review",
                "subject": _personal_key(courses.get(question.curriculum_version_id)),
                "question_type": question.question_type,
                "topic_id": spec.get("topic_id", question.topic_id),
                "subtopic_ids_json": json.dumps(list(subtopic_ids or [])),
                "difficulty": spec.get("difficulty", question.difficulty),
                "text": (
                    _embed_text(current_text[review.question_id], content) if edited else reviewed
                ),
                "original_text": reviewed if edited else None,
                "decision": review.decision,
                "reasons_json": review.reasons_json or "[]",
                "comment": (review.comment or "").strip() or None,
                "corrected_difficulty": review.corrected_difficulty,
                "corrected_subtopic_ids_json": review.corrected_subtopic_ids_json,
                "judge_verdicts_json": json.dumps(_verdicts(blob)),
                "rubric_version": blob.get("rubric_version"),
                "created_at": review.created_at,
            }
        )
    if episodes:
        bind.execute(
            sa.text(
                "INSERT INTO memory_episodes (review_id, question_id, source, subject, "
                "question_type, topic_id, subtopic_ids_json, difficulty, text, original_text, "
                "decision, reasons_json, comment, corrected_difficulty, "
                "corrected_subtopic_ids_json, judge_verdicts_json, rubric_version, created_at) "
                "VALUES (:review_id, :question_id, :source, :subject, :question_type, "
                ":topic_id, :subtopic_ids_json, :difficulty, :text, :original_text, :decision, "
                ":reasons_json, :comment, :corrected_difficulty, :corrected_subtopic_ids_json, "
                ":judge_verdicts_json, :rubric_version, :created_at)"
            ),
            episodes,
        )
