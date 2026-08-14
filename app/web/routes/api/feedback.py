"""Professor feedback endpoints: record a verdict and read the review history.

A review is an immutable record. An ``edit`` decision updates the question's
current fields but never touches the generated original (ADR-002), which is what
makes the before/after pair usable as preference evidence.

Each submitted review is also **routed** here (ADR-037): the judge gate is
crossed with the professor's verdict, the resulting cell is recorded as dataset
evidence, and the confirmed-bad cell relearns that type's instruction on the
spot. This module is where that happens because the routing spans three
subsystems -- feedback, calibration and personalization -- and the web layer is
the one allowed to reach across them (ADR-027).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.domain.enums import (
    JudgeMetricId,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.domain.feedback import REJECTION_REASON_LABELS
from app.errors import AdaptiveTrainerError
from app.evaluation.judge_learning import refresh_judge_prompt
from app.feedback import ReviewOutcome, route_review_outcome, submit_review
from app.generation.prompts import base_type_instruction
from app.persistence.repositories import JudgePromptRepository, ProfessorReviewRepository
from app.personalization import refresh_type_instruction
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    ReasonCount,
    ReviewListResponse,
    ReviewOut,
    ReviewOutcomeOut,
    ReviewRequest,
    ReviewStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


@router.post(
    "/questions/{question_id}/review", response_model=ReviewOut, status_code=status.HTTP_201_CREATED
)
def create_review(session: DbSession, question_id: int, payload: ReviewRequest) -> ReviewOut:
    """Record a professor verdict, then act on the cell it lands in (ADR-037)."""
    edit_fields: dict[str, str | None] = {}
    if payload.decision is ReviewDecision.EDIT:
        edit_fields = {
            "prompt": payload.prompt,
            "reference_solution": payload.reference_solution,
            "tests": payload.tests,
        }
    try:
        review = submit_review(
            session,
            question_id=question_id,
            decision=payload.decision,
            reasons=payload.reasons,
            comment=payload.comment or None,
            professor_id=payload.professor_id,
            **edit_fields,
        )
        outcome = route_review_outcome(session, review)
    except Exception:
        session.rollback()
        raise
    # Committed before the model call below: the review and its dataset row are
    # what the professor actually submitted, and they must survive a provider
    # failure that has nothing to do with them.
    session.commit()

    result = ReviewOut.from_row(review)
    if outcome is None:
        return result
    result.outcome = ReviewOutcomeOut.from_row(outcome.row)
    # Not exclusive. A ``missed`` review says two things at once: the generator
    # wrote a question the professor would not keep, and the judge passed it. One
    # lesson belongs to each, and dropping either would waste half the evidence
    # the professor just produced.
    if outcome.calls_for_instruction_refresh:
        _relearn_for(session, outcome, review.question.question_type, result.outcome)
    if outcome.calls_for_judge_repair:
        _relearn_judges(session, outcome, result.outcome)
    return result


def _record_error(outcome: ReviewOutcome, reported: ReviewOutcomeOut, detail: str) -> None:
    """Add one failure to the outcome, keeping any already recorded.

    Both relearners can run on the same review, so a failure must accumulate
    rather than overwrite: reporting only the later one would hide a generator
    refresh that never happened behind a judge repair that did.
    """
    existing = outcome.row.refresh_error
    combined = f"{existing}; {detail}" if existing else detail
    outcome.row.refresh_error = combined
    reported.refresh_error = combined


def _relearn_judges(session: DbSession, outcome: ReviewOutcome, reported: ReviewOutcomeOut) -> None:
    """Relearn each judge this review contradicted (ADR-039).

    The judge half of the routing. Only the judges named on the outcome are
    touched -- a judge nobody contradicted has learned nothing from this review,
    and rewriting it would change a measured behaviour on no evidence.

    This can run alongside :func:`_relearn_for` on the same review: a ``missed``
    review teaches the generator and the judge different lessons at once.

    A hand-written prompt is left alone. The professor typed it deliberately, and
    a learned rewrite renders onto the *shipped* text, so relearning would
    silently discard what they wrote.
    """
    if not outcome.attributed_metrics:
        return

    repository = JudgePromptRepository(session)
    refreshed: list[JudgeMetricId] = []
    errors: list[str] = []
    for metric in outcome.attributed_metrics:
        existing = repository.get(metric)
        if existing is not None and not existing.learned:
            logger.info("Judge %s is hand-written; leaving it alone.", metric.value)
            continue
        try:
            if refresh_judge_prompt(session, metric) is not None:
                refreshed.append(metric)
        except (AdaptiveTrainerError, OSError) as exc:
            session.rollback()
            errors.append(f"{metric.value}: {getattr(exc, 'message', None) or exc}")
            logger.warning("Relearning the %s judge failed: %s", metric.value, exc)

    outcome.row.judges_refreshed = refreshed
    if errors:
        _record_error(outcome, reported, "; ".join(errors))
    session.commit()
    reported.judges_refreshed = refreshed


def _relearn_for(
    session: DbSession,
    outcome: ReviewOutcome,
    question_type: QuestionType | None,
    reported: ReviewOutcomeOut,
) -> None:
    """Relearn one type's instruction because the professor did not accept it.

    Runs whenever the professor rejected or rewrote the question, in the
    ``confirmed_bad`` *and* ``missed`` cells. What the judge thought does not
    change the generator's lesson: in both cells the generator produced something
    the professor would not keep.

    Runs on the review that produced the cell, which is the point of ADR-037:
    the lesson reaches the generator before the next question is written rather
    than when someone remembers to press a button.

    A provider failure is recorded on the outcome row and reported, never
    raised. The review is already committed and is not in doubt; failing the
    request would tell the professor their verdict did not land. Reporting it is
    what stops the opposite error -- a silent failure that leaves the generator
    ignorant of a lesson the professor believes it has learned.
    """
    if question_type is None:
        return
    try:
        row = refresh_type_instruction(
            session,
            question_type,
            base_instruction=base_type_instruction(question_type),
        )
    except (AdaptiveTrainerError, OSError) as exc:
        session.rollback()
        detail = getattr(exc, "message", None) or str(exc)
        _record_error(outcome, reported, detail)
        session.commit()
        logger.warning(
            "Review %s landed in %s but relearning %s failed: %s",
            outcome.row.review_id,
            outcome.cell.value,
            question_type.value,
            detail,
        )
        return

    outcome.row.instruction_refreshed = row is not None
    session.commit()
    reported.instruction_refreshed = row is not None
    reported.refresh_rule_count = len(row.rules) if row is not None else None


@router.get("/reviews", response_model=ReviewListResponse)
def list_reviews(session: DbSession, limit: int = 50) -> ReviewListResponse:
    """The professor's review history, newest first."""
    repo = ProfessorReviewRepository(session)
    return ReviewListResponse(
        reviews=[ReviewOut.from_row(row) for row in repo.list_recent(limit=limit)],
        total=repo.count(),
    )


@router.get("/reviews/stats", response_model=ReviewStatsResponse)
def review_stats(session: DbSession) -> ReviewStatsResponse:
    """Decision totals and the rejection-reason distribution."""
    repo = ProfessorReviewRepository(session)
    by_decision = repo.count_by_decision()
    return ReviewStatsResponse(
        reviewed=repo.count(),
        approved=by_decision.get(ReviewDecision.APPROVE.value, 0),
        rejected=by_decision.get(ReviewDecision.REJECT.value, 0),
        edited=by_decision.get(ReviewDecision.EDIT.value, 0),
        reason_distribution=[
            ReasonCount(
                code=RejectionReason(code),
                label=REJECTION_REASON_LABELS[RejectionReason(code)],
                count=count,
            )
            # Most frequent first; ties broken by code so the order is stable.
            for code, count in sorted(
                repo.reason_counts().items(), key=lambda item: (-item[1], item[0])
            )
        ],
    )
