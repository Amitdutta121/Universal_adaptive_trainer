"""Professor feedback endpoints: record a verdict and read the review history.

A review is an immutable record. An ``edit`` decision updates the question's
current fields but never touches the generated original (ADR-002), which is what
makes the before/after pair usable as preference evidence.

Each submitted review is also **routed** here (ADR-037): the judge gate is
crossed with the professor's verdict and the resulting cell is recorded as
dataset evidence. Nothing here calls a model: what the review teaches the
generator and the judges is learned at the start of the next round
(:mod:`app.feedback.lessons`, ADR-063), so the professor never waits on it.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, status
from sqlalchemy import select

from app.domain.enums import RejectionReason, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS
from app.feedback import route_review_outcome, submit_review
from app.persistence.models import CurriculumVersionRow, ProfessorReviewRow, QuestionRow
from app.persistence.repositories import ProfessorReviewRepository
from app.web.routes.api.deps import (
    SPENDS_LLM_CREDIT,
    CourseScope,
    DbSession,
    question_in_course,
    subtopics_in_course,
)
from app.web.routes.api.schemas import (
    ReasonCount,
    ReviewListResponse,
    ReviewOut,
    ReviewOutcomeOut,
    ReviewRequest,
    ReviewStatsResponse,
)

router = APIRouter(tags=["feedback"])


@router.post(
    "/questions/{question_id}/review",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=SPENDS_LLM_CREDIT,
)
def create_review(
    session: DbSession, course: CourseScope, question_id: int, payload: ReviewRequest
) -> ReviewOut:
    """Record a professor verdict and the cell it lands in (ADR-037). No model call."""
    question_in_course(session, question_id, course)
    subtopics_in_course(session, payload.corrected_subtopic_ids or [], course)
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
            corrected_difficulty=payload.corrected_difficulty,
            corrected_subtopic_ids=payload.corrected_subtopic_ids,
            **edit_fields,
        )
        outcome = route_review_outcome(session, review)
    except Exception:
        session.rollback()
        raise
    session.commit()

    result = ReviewOut.from_row(review)
    if outcome is not None:
        result.outcome = ReviewOutcomeOut.from_row(outcome.row)
    return result


@router.get("/reviews", response_model=ReviewListResponse)
def list_reviews(session: DbSession, course: CourseScope, limit: int = 50) -> ReviewListResponse:
    """The professor's review history, newest first."""
    if course is not None:
        rows = _scoped_reviews(session, course)
        return ReviewListResponse(
            reviews=[ReviewOut.from_row(row) for row in rows[: max(0, limit)]], total=len(rows)
        )
    repo = ProfessorReviewRepository(session)
    return ReviewListResponse(
        reviews=[ReviewOut.from_row(row) for row in repo.list_recent(limit=limit)],
        total=repo.count(),
    )


@router.get("/reviews/stats", response_model=ReviewStatsResponse)
def review_stats(session: DbSession, course: CourseScope) -> ReviewStatsResponse:
    """Decision totals and the rejection-reason distribution."""
    repo = ProfessorReviewRepository(session)
    if course is None:
        by_decision = repo.count_by_decision()
        reason_counts = repo.reason_counts()
        reviewed = repo.count()
    else:
        rows = _scoped_reviews(session, course)
        by_decision = Counter(row.decision.value for row in rows)
        reason_counts = Counter(reason.value for row in rows for reason in row.reasons)
        reviewed = len(rows)
    return ReviewStatsResponse(
        reviewed=reviewed,
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
            for code, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    )


def _scoped_reviews(session: DbSession, course: int) -> list[ProfessorReviewRow]:
    return list(
        session.scalars(
            select(ProfessorReviewRow)
            .join(QuestionRow, ProfessorReviewRow.question_id == QuestionRow.id)
            .join(
                CurriculumVersionRow, QuestionRow.curriculum_version_id == CurriculumVersionRow.id
            )
            .where(CurriculumVersionRow.course_id == course)
            .order_by(ProfessorReviewRow.created_at.desc(), ProfessorReviewRow.id.desc())
        )
    )
