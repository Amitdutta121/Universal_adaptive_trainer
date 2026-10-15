"""Generation rounds: start the next round of a setup, and poll one.

``POST`` creates the round (``next_round``), commits, and schedules ``run_round`` as a
background task; the client polls ``GET /rounds/{id}`` until ``status`` is ``done`` or
``failed``. Generation never runs inside the request: the ``/api/*`` proxy would time it out.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.errors import DomainRuleError
from app.generation.rounds import next_round, run_round
from app.jobs.queue import JobQueue
from app.llm import StructuredLLMClient
from app.persistence.models import CurriculumVersionRow
from app.persistence.repositories import GenerationRoundRepository, QuestionSetupRepository
from app.web.routes.api.deps import CourseScope, DbSession, ensure_in_course
from app.web.routes.api.schemas import GenerationRoundOut, StartRoundResponse

router = APIRouter(prefix="/rounds", tags=["question-setup"])


def _ensure_setup_in_course(session: Session, setup_id: int, course: int | None) -> None:
    setup = QuestionSetupRepository(session).get(setup_id)
    version = session.get(CurriculumVersionRow, setup.curriculum_version_id)
    ensure_in_course(version.course_id if version else None, course, f"Question setup {setup_id}")


def queue_next_round(
    session: Session,
    course: int | None,
    setup_id: int,
    size: int,
    queue: JobQueue,
    client: StructuredLLMClient | None,
) -> StartRoundResponse:
    """Create the setup's next round, commit it and hand ``run_round`` to the queue."""
    _ensure_setup_in_course(session, setup_id, course)
    row = next_round(session, setup_id, size=size)
    if row.requested == 0:
        # Not committed: an empty round is an answer, not a row worth keeping.
        session.rollback()
        raise DomainRuleError(
            "Every cell has reached its target.",
            detail=(
                "No subtopic x difficulty cell of this setup is below its target, counting "
                "approved and pending questions. Review the pending questions first; rejected "
                "ones free their cell for the next round."
            ),
        )
    session.commit()
    queue.submit(run_round, row.id, client=client)
    return StartRoundResponse(round_id=row.id)


@router.get("/{round_id}", response_model=GenerationRoundOut)
def get_round(session: DbSession, course: CourseScope, round_id: int) -> GenerationRoundOut:
    """One round's status and progress counters."""
    row = GenerationRoundRepository(session).get(round_id)
    _ensure_setup_in_course(session, row.setup_id, course)
    return GenerationRoundOut.from_row(row)
