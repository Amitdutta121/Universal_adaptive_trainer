"""Which (taxonomy, style) scopes are trusted under a subject's current judge panel.

Trust is only counted for evaluations made under the same ``rubric_version``. A judge rewrite
renames the panel for every course of the subject, so callers that would rewrite a judge ask
this module first. Trust is computed on read; the newest question of each scope under the
current panel stands in for "a question of this scope judged now".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.judge_prompts import effective_rubric_version
from app.evaluation.trust import TrustReport, judge_trust
from app.persistence.models import QuestionRow
from app.subjects import SubjectProfile
from app.subjects.resolve import key_of_version, storage_keys_by_version


@dataclass(frozen=True)
class StyleTrust:
    curriculum_version_id: int
    style_id: str
    report: TrustReport


def style_trust_under_current_panel(
    session: Session,
    profile: SubjectProfile,
    *,
    curriculum_version_ids: set[int] | None = None,
) -> list[StyleTrust]:
    """Trust per (taxonomy, style) of this subject, judged under the panel in force now."""
    rubric = effective_rubric_version(session, profile=profile)
    stmt = select(QuestionRow).where(
        QuestionRow.style_id.is_not(None),
        QuestionRow.curriculum_version_id.is_not(None),
    )
    if curriculum_version_ids is not None:
        stmt = stmt.where(QuestionRow.curriculum_version_id.in_(curriculum_version_ids))
    stmt = stmt.order_by(QuestionRow.created_at.desc(), QuestionRow.id.desc())
    rows = list(session.scalars(stmt))
    keys = storage_keys_by_version(session, {row.curriculum_version_id for row in rows})
    newest: dict[tuple[int, str], QuestionRow] = {}
    for row in rows:
        if key_of_version(keys, row.curriculum_version_id) != profile.personal_key:
            continue
        if (row.pedagogical_eval or {}).get("rubric_version") != rubric:
            continue
        newest.setdefault((row.curriculum_version_id, row.style_id), row)
    return [
        StyleTrust(version_id, style_id, judge_trust(session, row, None))
        for (version_id, style_id), row in sorted(newest.items())
    ]


def trusted_scopes(session: Session, profile: SubjectProfile) -> list[StyleTrust]:
    """The scopes whose questions skip professor review under the current panel."""
    scopes = style_trust_under_current_panel(session, profile)
    return [item for item in scopes if item.report.trusted]
