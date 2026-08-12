"""Professor feedback endpoints: record a verdict and read the review history.

A review is an immutable record. An ``edit`` decision updates the question's
current fields but never touches the generated original (ADR-002), which is what
makes the before/after pair usable as preference evidence.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.domain.enums import RejectionReason, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS
from app.feedback import submit_review
from app.persistence.repositories import ProfessorReviewRepository
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    ReasonCount,
    ReviewListResponse,
    ReviewOut,
    ReviewRequest,
    ReviewStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


@router.post(
    "/questions/{question_id}/review", response_model=ReviewOut, status_code=status.HTTP_201_CREATED
)
def create_review(session: DbSession, question_id: int, payload: ReviewRequest) -> ReviewOut:
    """Record a professor verdict on one generated question."""
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
    except Exception:
        session.rollback()
        raise
    session.commit()
    return ReviewOut.from_row(review)


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
