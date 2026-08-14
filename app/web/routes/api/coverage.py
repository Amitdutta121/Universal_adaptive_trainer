"""Coverage of the taxonomy by approved questions, and frozen question sets.

Reading a grid is free and changes nothing. Freezing a set writes rows, so it is
a POST the professor triggers deliberately -- and once written, a set is never
edited (ADR-036).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.coverage import build_coverage_report, create_question_set
from app.persistence.repositories import QuestionSetRepository
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    CoverageReportResponse,
    CreateQuestionSetRequest,
    QuestionSetListResponse,
    QuestionSetOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["coverage"])


@router.get("/coverage", response_model=CoverageReportResponse)
def coverage(session: DbSession, set_version_id: int | None = None) -> CoverageReportResponse:
    """The subtopic x difficulty grid over approved questions.

    Without ``set_version_id`` this is the live bank -- what to generate next.
    With one it is that frozen set -- what a training run would actually serve.
    """
    return CoverageReportResponse.from_report(
        build_coverage_report(session, set_version_id=set_version_id)
    )


@router.get("/question-sets", response_model=QuestionSetListResponse)
def list_question_sets(session: DbSession) -> QuestionSetListResponse:
    rows = QuestionSetRepository(session).list_versions()
    return QuestionSetListResponse(
        sets=[QuestionSetOut.from_row(row) for row in rows],
        total=len(rows),
    )


@router.get("/question-sets/{set_version_id}", response_model=QuestionSetOut)
def get_question_set(session: DbSession, set_version_id: int) -> QuestionSetOut:
    return QuestionSetOut.from_row(QuestionSetRepository(session).get(set_version_id))


@router.post(
    "/question-sets",
    response_model=QuestionSetOut,
    status_code=status.HTTP_201_CREATED,
)
def create_set(session: DbSession, payload: CreateQuestionSetRequest) -> QuestionSetOut:
    """Freeze every approved question of the approved curriculum under a name."""
    row = create_question_set(session, label=payload.label, notes=payload.notes)
    return QuestionSetOut.from_row(row)
