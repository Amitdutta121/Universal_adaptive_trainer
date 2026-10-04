"""Reading and editing the four judge prompts (ADR-038).

A judge is repaired by rewriting its prompt. Until this existed the repair was a
source edit and a redeploy, which meant the held-back check questions ADR-035
reserves had nothing to score: the professor could measure a judge but not
change one.

Saving re-names the panel. Every evaluation written afterwards carries the new
``rubric_version``, so calibration reports the repaired judge separately from
the one it replaced instead of pooling both into a single agreement figure.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.domain.enums import JudgeMetricId
from app.errors import DomainRuleError, NotFoundError
from app.evaluation.judge_learning import disagreements_for, refresh_judge_prompt
from app.evaluation.judge_prompts import effective_rubric_version, resolve_system_prompts
from app.evaluation.prompts import rubric_version_for, system_prompt_for
from app.evaluation.trust_scope import trusted_scopes
from app.persistence.models import JudgePromptRow
from app.persistence.repositories import JudgePromptRepository
from app.subjects import SubjectProfile
from app.web.routes.api.deps import CourseProfile, DbSession
from app.web.routes.api.schemas import (
    JudgePromptListResponse,
    JudgePromptOut,
    JudgePromptRefreshResponse,
    JudgePromptRequest,
    JudgePromptSaveResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/judge-prompts", tags=["judge-prompts"])


def _out(
    metric: JudgeMetricId,
    row: JudgePromptRow | None,
    profile: SubjectProfile,
    *,
    available: int = 0,
) -> JudgePromptOut:
    shipped = system_prompt_for(metric, profile)
    return JudgePromptOut(
        metric=metric,
        label=metric.value.replace("_", " "),
        system_prompt=row.system_prompt if row else shipped,
        shipped_prompt=shipped,
        edited=row is not None,
        learned=row.learned if row else False,
        rules=[str(rule.get("rule", "")) for rule in (row.rules if row else [])],
        evidence_count=row.evidence_count if row else 0,
        available_disagreements=available,
        revision=row.revision if row else 0,
        note=row.note if row else None,
        updated_at=(row.updated_at or row.created_at) if row else None,
    )


@router.get("", response_model=JudgePromptListResponse)
def list_judge_prompts(session: DbSession, profile: CourseProfile) -> JudgePromptListResponse:
    """All four judges of this course's subject: the text each runs and the text it shipped with."""
    stored = {
        row.metric: row
        for row in JudgePromptRepository(session).list_all(subject=profile.storage_key)
    }
    return JudgePromptListResponse(
        prompts=[
            _out(
                metric,
                stored.get(metric),
                profile,
                available=len(disagreements_for(session, metric, profile=profile)),
            )
            for metric in JudgeMetricId
        ],
        rubric_version=effective_rubric_version(session, profile=profile),
        shipped_rubric_version=rubric_version_for(profile),
    )


@router.put("/{metric}", response_model=JudgePromptSaveResponse)
def save_judge_prompt(
    session: DbSession, metric: JudgeMetricId, payload: JudgePromptRequest, profile: CourseProfile
) -> JudgePromptSaveResponse:
    """Replace one judge's system prompt, and re-name the panel.

    Existing evaluations are left alone. Re-judging the bank under the new prompt
    is a separate, explicit act (ADR-030) -- rewriting stored verdicts here would
    destroy the very pairs the repair is supposed to be scored against.
    """
    before = effective_rubric_version(session, profile=profile)
    text = payload.system_prompt.strip()
    try:
        row = JudgePromptRepository(session).save(
            metric,
            subject=profile.storage_key,
            system_prompt=text,
            note=(payload.note or "").strip() or None,
        )
    except Exception:
        session.rollback()
        raise
    session.commit()

    after = effective_rubric_version(session, profile=profile)
    logger.info(
        "Judge %s edited (revision %s). Rubric version %s -> %s.",
        metric.value,
        row.revision,
        before,
        after,
    )
    return JudgePromptSaveResponse(
        prompt=_out(metric, row, profile),
        rubric_version=after,
        rubric_version_changed=after != before,
    )


@router.delete("/{metric}", response_model=JudgePromptSaveResponse)
def revert_judge_prompt(
    session: DbSession, metric: JudgeMetricId, profile: CourseProfile
) -> JudgePromptSaveResponse:
    """Drop one override so the judge runs its shipped prompt again."""
    before = effective_rubric_version(session, profile=profile)
    repository = JudgePromptRepository(session)
    if not repository.delete(metric, subject=profile.storage_key):
        raise NotFoundError(
            f"The {metric.value} judge is already running its shipped prompt.",
            detail="There is no override to revert.",
        )
    session.commit()

    after = effective_rubric_version(session, profile=profile)
    logger.info("Judge %s reverted. Rubric version %s -> %s.", metric.value, before, after)
    return JudgePromptSaveResponse(
        prompt=_out(metric, None, profile),
        rubric_version=after,
        rubric_version_changed=after != before,
    )


def current_prompts(session: DbSession, profile: SubjectProfile) -> dict[JudgeMetricId, str]:
    """The prompt set in force, for callers that need the text rather than the API shape."""
    return resolve_system_prompts(session, profile=profile)


@router.post("/{metric}/refresh", response_model=JudgePromptRefreshResponse)
def refresh(
    session: DbSession, metric: JudgeMetricId, profile: CourseProfile
) -> JudgePromptRefreshResponse:
    """Re-learn one judge's prompt from the questions it got wrong (ADR-039).

    The mirror of ``POST /api/instructions/{question_type}/refresh``. Reads only
    the disagreements this judge is named in, minus the held-out third, so the
    reserved questions stay available to score the result.
    """
    trusted = trusted_scopes(session, profile)
    if trusted:
        raise DomainRuleError(
            "Judge learning is paused while questions skip review.",
            detail=(
                f"{len(trusted)} style(s) are trusted under the current judges. A rewrite would "
                "send them all back to review; edit the prompt by hand if that is intended."
            ),
        )
    before = effective_rubric_version(session, profile=profile)
    try:
        row = refresh_judge_prompt(session, metric, profile=profile)
    except Exception:
        session.rollback()
        raise

    available = len(disagreements_for(session, metric, profile=profile))
    if row is None:
        return JudgePromptRefreshResponse(
            prompt=_out(
                metric,
                JudgePromptRepository(session).get(metric, subject=profile.storage_key),
                profile,
                available=available,
            ),
            rubric_version=before,
            rubric_version_changed=False,
            learned=False,
            rule_count=0,
            evidence_count=0,
        )

    after = effective_rubric_version(session, profile=profile)
    return JudgePromptRefreshResponse(
        prompt=_out(metric, row, profile, available=available),
        rubric_version=after,
        rubric_version_changed=after != before,
        learned=True,
        rule_count=len(row.rules),
        evidence_count=row.evidence_count,
    )
