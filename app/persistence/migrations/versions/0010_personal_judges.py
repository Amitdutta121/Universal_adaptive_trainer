"""Judge edits and learned instructions belong to the professor, not to the whole subject.

Rows keyed by a preset (``intro_python``, ``physics``, ...) were shared by every course of
that subject (ADR-056). They are now keyed ``<preset>@<owner hex>`` (ADR-059): each row is
copied to every professor who owns a course of that subject, then the shared row is
removed. A preset no owned course uses keeps its row, which only an ownerless request reads.
``custom:<course id>`` rows are already one course's own and are left alone.
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0010_personal_judges"
down_revision = "0009_course_access"
branch_labels = None
depends_on = None

LEGACY_SUBJECT = "intro_python"
TABLES = ("judge_prompts", "type_instructions")


def _owners_by_subject(bind: sa.Connection) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    rows = bind.execute(
        sa.text(
            "SELECT coalesce(subject, :legacy), owner_id FROM courses WHERE owner_id IS NOT NULL"
        ),
        {"legacy": LEGACY_SUBJECT},
    )
    for subject, owner in rows:
        owners.setdefault(subject, set()).add(uuid.UUID(str(owner)).hex)
    return owners


def upgrade() -> None:
    bind = op.get_bind()
    owners = _owners_by_subject(bind)
    for name in TABLES:
        table = sa.Table(name, sa.MetaData(), autoload_with=bind)
        shared = [
            row._asdict()
            for row in bind.execute(sa.select(table))
            if ":" not in row.subject and "@" not in row.subject
        ]
        for row in shared:
            subject_owners = owners.get(row["subject"], set())
            if not subject_owners:
                continue
            for owner in sorted(subject_owners):
                copy = {key: value for key, value in row.items() if key != "id"}
                copy["subject"] = f"{row['subject']}@{owner}"
                bind.execute(table.insert().values(**copy))
            bind.execute(table.delete().where(table.c.id == row["id"]))


def downgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        table = sa.Table(name, sa.MetaData(), autoload_with=bind)
        personal = [row._asdict() for row in bind.execute(sa.select(table))]
        seen: set[tuple] = set()
        for row in personal:
            if "@" not in row["subject"]:
                continue
            preset = row["subject"].split("@", 1)[0]
            other = next(key for key in ("metric", "question_type") if key in row)
            if (preset, row[other]) in seen:
                bind.execute(table.delete().where(table.c.id == row["id"]))
                continue
            seen.add((preset, row[other]))
            bind.execute(table.update().where(table.c.id == row["id"]).values(subject=preset))
