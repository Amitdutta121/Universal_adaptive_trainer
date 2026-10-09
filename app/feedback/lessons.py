"""The lesson run: learn from the reviews since the last round, once, before it generates.

ADR-063 step 1-2. Saving a review only records it (review, outcome); the model calls that
turn reviews into lessons happen here, in the round's background job, so the review screen
never waits on a provider. Each affected judge and each affected question type is relearned
**once** per run however many reviews named it -- the existing learners already read every
review of their scope, so one call per scope sees all the new evidence.

Judges learn as in ADR-039 (:func:`refresh_judge_prompt` for the judges a review contradicted;
m11 moves them to memory). The generator learns **guidelines** (ADR-063 points 3-4, m5): for
each type the professor rejected or rewrote, one :func:`~app.memory.distill_guidelines` call
turns the new reviews into edit operations on that type's guidelines. Judges first, then the
generator (ADR-063's order).

A provider failure is recorded on the outcome rows it concerns and returned, never raised:
the round must still generate, and a silent failure would leave the professor believing a
lesson landed that did not. Those rows stay pending, so the next round tries again.

Allowed dependencies
    Those of :mod:`app.feedback`, plus the judge learner of ``app.evaluation`` and the
    guideline distiller of ``app.memory``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import JudgeMetricId, QuestionType
from app.errors import AdaptiveTrainerError
from app.evaluation.judge_learning import refresh_judge_prompt
from app.evaluation.trust_scope import trusted_scopes
from app.feedback.outcomes import _outcome_from_row
from app.llm import StructuredLLMClient
from app.memory import distill_guidelines, generator_target
from app.persistence.models import ReviewOutcomeRow
from app.persistence.repositories import JudgePromptRepository, ReviewOutcomeRepository
from app.subjects import SubjectProfile
from app.subjects.resolve import key_of_version, storage_keys_by_version

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LessonRun:
    """What one lesson run did: how many reviews it learned from, and what failed.

    ``applied`` excludes the reviews whose lesson failed; they stay pending.
    """

    applied: int = 0
    error: str | None = None


def apply_pending_lessons(
    session: Session,
    *,
    round_id: int,
    profile: SubjectProfile,
    client: StructuredLLMClient | None = None,
) -> LessonRun:
    """Learn from every pending review of ``profile``'s subject and mark it learned.

    Only reviews of questions in the same subject key as the round (ADR-059): those are the
    reviews the learners read for this subject, so another course's reviews stay pending for
    its own next round. Commits as it goes.
    """
    pending = _pending_for(session, profile)
    if not pending:
        return LessonRun()

    settings = get_settings()
    errors: list[str] = []
    failed: set[int] = set()
    if settings.judge_learning_enabled:
        errors += _learn_judges(session, pending, profile, client, failed)
    if settings.generator_learning_enabled:
        errors += _learn_generator(session, pending, profile, round_id, client, failed)

    learned = [row for row in pending if row.id not in failed]
    for row in learned:
        row.lessons_round_id = round_id
    session.commit()
    logger.info("round %s: applied lessons from %s review(s)", round_id, len(learned))
    return LessonRun(applied=len(learned), error="; ".join(errors) or None)


def _pending_for(session: Session, profile: SubjectProfile) -> list[ReviewOutcomeRow]:
    rows = ReviewOutcomeRepository(session).list_pending_lessons()
    keys = storage_keys_by_version(
        session,
        {
            row.question.curriculum_version_id
            for row in rows
            if row.question.curriculum_version_id is not None
        },
    )
    return [
        row
        for row in rows
        if key_of_version(keys, row.question.curriculum_version_id) == profile.personal_key
    ]


def _record_error(row: ReviewOutcomeRow, detail: str) -> None:
    """Add one failure to the row, keeping any already recorded.

    Both learners can fail on the same review (a ``missed`` one teaches both), so a
    failure accumulates rather than overwrites.
    """
    row.refresh_error = f"{row.refresh_error}; {detail}" if row.refresh_error else detail


def _learn_judges(
    session: Session,
    rows: list[ReviewOutcomeRow],
    profile: SubjectProfile,
    client: StructuredLLMClient | None,
    failed_rows: set[int] | None = None,
) -> list[str]:
    """Relearn each judge a pending review contradicted, once (ADR-039).

    Only judges named on an outcome are touched -- a judge nobody contradicted has learned
    nothing, and rewriting it would change a measured behaviour on no evidence. A
    hand-written prompt is left alone: a learned rewrite renders onto the *shipped* text and
    would silently discard what the professor typed. Paused while any style of this subject
    is trusted under the current panel (docs/TRUST_AND_JUDGE_STATS_PLAN.md).
    """
    named = [row for row in rows if _outcome_from_row(row).calls_for_judge_repair]
    metrics = list(
        dict.fromkeys(metric for row in named for metric in row.attributed_metrics or [])
    )
    if not metrics:
        return []
    trusted = trusted_scopes(session, profile)
    if trusted:
        # A rewrite renames the panel and every trusted style would fall back to review.
        logger.info(
            "Judge learning paused: %s style(s) trusted under the current panel.", len(trusted)
        )
        for row in named:
            row.judges_refreshed = []
        return []

    repository = JudgePromptRepository(session)
    refreshed: list[JudgeMetricId] = []
    failed: dict[JudgeMetricId, str] = {}
    for metric in metrics:
        existing = repository.get(metric, subject=profile.personal_key)
        if existing is not None and not existing.learned:
            logger.info("Judge %s is hand-written; leaving it alone.", metric.value)
            continue
        try:
            if refresh_judge_prompt(session, metric, client=client, profile=profile) is not None:
                refreshed.append(metric)
            session.commit()
        except (AdaptiveTrainerError, OSError) as exc:
            session.rollback()
            failed[metric] = f"{metric.value}: {getattr(exc, 'message', None) or exc}"
            logger.warning("Relearning the %s judge failed: %s", metric.value, exc)

    for row in named:
        attributed = list(row.attributed_metrics or [])
        row.judges_refreshed = [metric for metric in refreshed if metric in attributed]
        errors = [failed[metric] for metric in attributed if metric in failed]
        if errors:
            _record_error(row, "; ".join(errors))
            if failed_rows is not None:
                failed_rows.add(row.id)
    session.commit()
    return list(failed.values())


def _learn_generator(
    session: Session,
    rows: list[ReviewOutcomeRow],
    profile: SubjectProfile,
    round_id: int,
    client: StructuredLLMClient | None,
    failed_rows: set[int],
) -> list[str]:
    """Distil each type whose questions the professor did not accept into guidelines, once.

    Both the ``confirmed_bad`` and the ``missed`` cell: what the judge thought does not
    change the generator's lesson (ADR-037). The evidence is only this run's reviews of the
    type; what earlier reviews taught is already in the guidelines the distiller edits.
    """
    by_type: dict[QuestionType, list[ReviewOutcomeRow]] = {}
    for row in rows:
        if row.question_type is not None and _outcome_from_row(row).calls_for_instruction_refresh:
            by_type.setdefault(row.question_type, []).append(row)

    errors: list[str] = []
    for question_type, of_type in by_type.items():
        try:
            learned = distill_guidelines(
                session,
                target=generator_target(question_type),
                subject=profile.personal_key,
                question_type=question_type,
                review_ids=[row.review_id for row in of_type],
                round_id=round_id,
                client=client,
            )
            session.commit()
        except (AdaptiveTrainerError, OSError) as exc:
            session.rollback()
            detail = getattr(exc, "message", None) or str(exc)
            for row in of_type:
                _record_error(row, detail)
                failed_rows.add(row.id)
            session.commit()
            errors.append(f"{question_type.value}: {detail}")
            logger.warning("Relearning %s failed: %s", question_type.value, detail)
            continue
        for row in of_type:
            row.instruction_refreshed = learned.changed
        session.commit()
    return errors
