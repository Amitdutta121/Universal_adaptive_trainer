"""What the generator is told per question type, and the guidelines learned for it (ADR-063).

``GET /instructions`` shows, for every built type, the shipped instruction plus the **active**
guidelines -- exactly the text the generator receives. The guidelines themselves are listed
and confirmed or deleted under ``/guidelines``. Nothing here calls a model: guidelines are
learned by the lesson run at the start of each round (``app.feedback.lessons``), so the
manual "refresh" and rule-index deletes of the rewritten rule list (ADR-033) are gone.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.domain.enums import GuidelineStatus, QuestionType
from app.generation.prompts import base_type_instruction
from app.memory import (
    ACTIVE_SUPPORT,
    MemoryGuidelineRepository,
    active_guidelines,
    confirm_guideline,
    delete_guideline,
    generator_target,
    render_with_guidelines,
)
from app.personalization import reviews_for_type
from app.question_types import implemented_types
from app.subjects import SubjectProfile
from app.web.routes.api.deps import CourseProfile, DbSession
from app.web.routes.api.schemas import (
    GuidelineListResponse,
    GuidelineOut,
    TypeInstructionListResponse,
    TypeInstructionOut,
)

router = APIRouter(prefix="/instructions", tags=["instructions"])
guidelines_router = APIRouter(prefix="/guidelines", tags=["instructions"])


def _out(
    session: DbSession, profile: SubjectProfile, question_type: QuestionType
) -> TypeInstructionOut:
    rows = active_guidelines(
        session, target=generator_target(question_type), subject=profile.personal_key
    )
    updated = [row.updated_at or row.created_at for row in rows]
    return TypeInstructionOut(
        question_type=question_type,
        instruction=render_with_guidelines(
            base_type_instruction(question_type), [row.text for row in rows]
        ),
        rules=[row.text for row in rows],
        learned=bool(rows),
        review_count=len({review for row in rows for review in row.review_ids or []}),
        available_reviews=len(
            reviews_for_type(session, question_type, subject=profile.personal_key)
        ),
        updated_at=max(updated) if updated else None,
    )


@router.get("", response_model=TypeInstructionListResponse)
def list_instructions(session: DbSession, profile: CourseProfile) -> TypeInstructionListResponse:
    """Every built question type, with the instruction its generator receives now."""
    return TypeInstructionListResponse(
        instructions=[
            _out(session, profile, question_type) for question_type in implemented_types()
        ]
    )


@guidelines_router.get("", response_model=GuidelineListResponse)
def list_guidelines(session: DbSession, profile: CourseProfile) -> GuidelineListResponse:
    """The course subject's pending and active guidelines, oldest first."""
    rows = MemoryGuidelineRepository(session).list_for(
        subject=profile.personal_key,
        statuses=[GuidelineStatus.PENDING, GuidelineStatus.ACTIVE],
    )
    return GuidelineListResponse(
        active_support=ACTIVE_SUPPORT, guidelines=[GuidelineOut.from_row(row) for row in rows]
    )


@guidelines_router.post("/{guideline_id}/confirm", response_model=GuidelineOut)
def confirm(session: DbSession, profile: CourseProfile, guideline_id: int) -> GuidelineOut:
    """The professor vouches for a guideline: it is sent from the next generation.

    An output-contract guideline stays refused even when confirmed.
    """
    row = confirm_guideline(session, guideline_id, subject=profile.personal_key)
    session.commit()
    return GuidelineOut.from_row(row)


@guidelines_router.delete("/{guideline_id}", response_model=GuidelineOut)
def delete(session: DbSession, profile: CourseProfile, guideline_id: int) -> GuidelineOut:
    """Retire a guideline: never sent again, and the distiller no longer sees it."""
    row = delete_guideline(session, guideline_id, subject=profile.personal_key)
    session.commit()
    return GuidelineOut.from_row(row)
