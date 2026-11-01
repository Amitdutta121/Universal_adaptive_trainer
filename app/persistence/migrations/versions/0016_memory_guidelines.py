"""Memory guidelines replace the rewritten rule lists; rounds record a drift warning (ADR-063).

Every learned rule in ``type_instructions`` becomes a ``generator:<type>`` guideline of the same
subject, keeping the reviews it cited. A rule citing at least two distinct reviews is active; any
other is pending, so a rule one review created (the "always option A" case) stops reaching the
generator until a second review or the professor confirms it. ``type_instructions`` is left in
place, unread, so a downgrade loses nothing.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0016_memory_guidelines"
down_revision = "0015_memory_episodes"
branch_labels = None
depends_on = None

#: Frozen here, not imported: a migration must keep meaning what it meant when it was written.
ACTIVE_SUPPORT = 2


def upgrade() -> None:
    op.create_table(
        "memory_guidelines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=100), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("review_ids_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confirmed_by_professor", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_round_id", sa.Integer(), nullable=True),
        sa.Column("updated_round_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memory_guidelines_target"), "memory_guidelines", ["target"])
    op.create_index(op.f("ix_memory_guidelines_subject"), "memory_guidelines", ["subject"])
    op.create_index(op.f("ix_memory_guidelines_status"), "memory_guidelines", ["status"])
    op.add_column("generation_rounds", sa.Column("drift_warning", sa.Text(), nullable=True))
    _migrate_rules(op.get_bind())


def downgrade() -> None:
    with op.batch_alter_table("generation_rounds") as batch:
        batch.drop_column("drift_warning")
    op.drop_index(op.f("ix_memory_guidelines_status"), table_name="memory_guidelines")
    op.drop_index(op.f("ix_memory_guidelines_subject"), table_name="memory_guidelines")
    op.drop_index(op.f("ix_memory_guidelines_target"), table_name="memory_guidelines")
    op.drop_table("memory_guidelines")


def _review_ids(value: Any) -> list[int]:
    """The distinct integer review ids a stored rule cited, in order."""
    ids: list[int] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, int) and not isinstance(item, bool) and item not in ids:
            ids.append(item)
    return ids


def _migrate_rules(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text("SELECT subject, question_type, rules_json FROM type_instructions")
    ).fetchall()
    insert = sa.text(
        "INSERT INTO memory_guidelines (target, subject, text, review_ids_json, status, "
        "confirmed_by_professor, created_at, updated_at) "
        "VALUES (:target, :subject, :text, :review_ids, :status, 0, CURRENT_TIMESTAMP, "
        "CURRENT_TIMESTAMP)"
    )
    for subject, question_type, rules_json in rows:
        try:
            rules = json.loads(rules_json) if rules_json else []
        except ValueError:
            rules = []
        for rule in rules if isinstance(rules, list) else []:
            text = str(rule.get("rule", "")).strip() if isinstance(rule, dict) else ""
            if not text:
                continue
            ids = _review_ids(rule.get("review_ids"))
            connection.execute(
                insert,
                {
                    "target": f"generator:{question_type}",
                    "subject": subject,
                    "text": text,
                    "review_ids": json.dumps(ids),
                    "status": "active" if len(ids) >= ACTIVE_SUPPORT else "pending",
                },
            )
