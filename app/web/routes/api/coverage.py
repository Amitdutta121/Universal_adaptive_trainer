"""Coverage of the taxonomy by approved questions, and frozen question sets.

Reading a grid is free and changes nothing. Freezing a set writes rows, so it is
a POST the professor triggers deliberately -- and once written, a set is never
edited (ADR-036).
"""

from __future__ import annotations

import logging
from typing import NoReturn

from fastapi import APIRouter, status

from app.coverage import build_coverage_report, create_question_set
from app.errors import FeatureNotAvailableError
from app.persistence.repositories import QuestionSetRepository
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    CoverageReportResponse,
    CreateQuestionSetRequest,
    FillGapsRequest,
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


@router.post(
    "/coverage/generation-runs",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    # This handler only ever raises, so there is no schema to derive from its
    # return annotation.
    response_model=None,
)
def start_generation_run(payload: FillGapsRequest) -> NoReturn:
    """Not implemented. Selecting gaps is real; acting on them is not.

    The step this endpoint would perform does not exist. A professor selects a
    chunk, a difficulty and a question type, and the *generator* decides which
    topic and subtopics it wrote for (ADR-031) -- so a named gap cannot be
    requested. Closing one means finding chunks that teach that subtopic,
    generating from them, and seeing what the generator claimed afterwards.

    Nothing ranks chunks by subtopic yet. Returning a plausible-looking run here
    would report targeted generation that never happened, so it refuses instead.
    """
    raise FeatureNotAvailableError(
        f"{len(payload.targets)} coverage gap(s) were selected, but generating for a named "
        "subtopic is not built. The generator classifies what it wrote (ADR-031); it cannot be "
        "aimed. Nothing ranks textbook chunks by the subtopic they teach yet, so there is no "
        "honest way to start a targeted run. Generate from a chunk on the questions page, then "
        "check what the generator claimed."
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
