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
from app.errors import NotFoundError
from app.evaluation.judge_learning import disagreements_for, refresh_judge_prompt
from app.evaluation.judge_prompts import effective_rubric_version, resolve_system_prompts
from app.evaluation.prompts import RUBRIC_VERSION, SYSTEM_PROMPT_FOR
from app.persistence.models import JudgePromptRow
from app.persistence.repositories import JudgePromptRepository
from app.web.routes.api.deps import DbSession
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
    metric: JudgeMetricId, row: JudgePromptRow | None, *, available: int = 0
) -> JudgePromptOut:
    return JudgePromptOut(
        metric=metric,
        label=metric.value.replace("_", " "),
        system_prompt=row.system_prompt if row else SYSTEM_PROMPT_FOR[metric],
        shipped_prompt=SYSTEM_PROMPT_FOR[metric],
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
def list_judge_prompts(session: DbSession) -> JudgePromptListResponse:
    """All four judges, each with the text it runs and the text it shipped with."""
    stored = {row.metric: row for row in JudgePromptRepository(session).list_all()}
    return JudgePromptListResponse(
        prompts=[
            _out(metric, stored.get(metric), available=len(disagreements_for(session, metric)))
            for metric in JudgeMetricId
        ],
        rubric_version=effective_rubric_version(session),
        shipped_rubric_version=RUBRIC_VERSION,
    )


@router.put("/{metric}", response_model=JudgePromptSaveResponse)
def save_judge_prompt(
    session: DbSession, metric: JudgeMetricId, payload: JudgePromptRequest
) -> JudgePromptSaveResponse:
    """Replace one judge's system prompt, and re-name the panel.

    Existing evaluations are left alone. Re-judging the bank under the new prompt
    is a separate, explicit act (ADR-030) -- rewriting stored verdicts here would
    destroy the very pairs the repair is supposed to be scored against.
    """
    before = effective_rubric_version(session)
    text = payload.system_prompt.strip()
    try:
        row = JudgePromptRepository(session).save(
            metric, system_prompt=text, note=(payload.note or "").strip() or None
        )
    except Exception:
        session.rollback()
        raise
    session.commit()

    after = effective_rubric_version(session)
    logger.info(
        "Judge %s edited (revision %s). Rubric version %s -> %s.",
        metric.value,
        row.revision,
        before,
        after,
    )
    return JudgePromptSaveResponse(
        prompt=_out(metric, row),
        rubric_version=after,
        rubric_version_changed=after != before,
    )


@router.delete("/{metric}", response_model=JudgePromptSaveResponse)
def revert_judge_prompt(session: DbSession, metric: JudgeMetricId) -> JudgePromptSaveResponse:
    """Drop one override so the judge runs its shipped prompt again."""
    before = effective_rubric_version(session)
    repository = JudgePromptRepository(session)
    if not repository.delete(metric):
        raise NotFoundError(
            f"The {metric.value} judge is already running its shipped prompt.",
            detail="There is no override to revert.",
        )
    session.commit()

    after = effective_rubric_version(session)
    logger.info("Judge %s reverted. Rubric version %s -> %s.", metric.value, before, after)
    return JudgePromptSaveResponse(
        prompt=_out(metric, None),
        rubric_version=after,
        rubric_version_changed=after != before,
    )


def current_prompts(session: DbSession) -> dict[JudgeMetricId, str]:
    """The prompt set in force, for callers that need the text rather than the API shape."""
    return resolve_system_prompts(session)


@router.post("/{metric}/refresh", response_model=JudgePromptRefreshResponse)
def refresh(session: DbSession, metric: JudgeMetricId) -> JudgePromptRefreshResponse:
    """Re-learn one judge's prompt from the questions it got wrong (ADR-039).

    The mirror of ``POST /api/instructions/{question_type}/refresh``. Reads only
    the disagreements this judge is named in, minus the held-out third, so the
    reserved questions stay available to score the result.
    """
    before = effective_rubric_version(session)
    try:
        row = refresh_judge_prompt(session, metric)
    except Exception:
        session.rollback()
        raise

    available = len(disagreements_for(session, metric))
    if row is None:
        return JudgePromptRefreshResponse(
            prompt=_out(metric, JudgePromptRepository(session).get(metric), available=available),
            rubric_version=before,
            rubric_version_changed=False,
            learned=False,
            rule_count=0,
            evidence_count=0,
        )

    after = effective_rubric_version(session)
    return JudgePromptRefreshResponse(
        prompt=_out(metric, row, available=available),
        rubric_version=after,
        rubric_version_changed=after != before,
        learned=True,
        rule_count=len(row.rules),
        evidence_count=row.evidence_count,
    )
