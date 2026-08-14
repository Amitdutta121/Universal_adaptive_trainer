"""Per-type generation instructions learned from professor reviews (ADR-033).

Reading them is free. Refreshing one costs a model call, so it is a POST the
professor triggers rather than something that happens behind a review.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.domain.enums import QuestionType
from app.generation.prompts import base_type_instruction
from app.persistence.repositories import TypeInstructionRepository
from app.personalization import refresh_type_instruction, reviews_for_type
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    TypeInstructionListResponse,
    TypeInstructionOut,
    TypeInstructionRefreshResponse,
)

router = APIRouter(prefix="/instructions", tags=["instructions"])


@router.get("", response_model=TypeInstructionListResponse)
def list_instructions(session: DbSession) -> TypeInstructionListResponse:
    """Every question type, with whatever has been learned for it.

    Types with nothing learned are listed too, carrying the shipped instruction
    and a review count -- that is how a professor sees which types have enough
    feedback to be worth refreshing.
    """
    repository = TypeInstructionRepository(session)
    stored = {row.question_type: row for row in repository.list_all()}
    entries = []
    for question_type in QuestionType:
        row = stored.get(question_type)
        entries.append(
            TypeInstructionOut(
                question_type=question_type,
                instruction=row.instruction if row else base_type_instruction(question_type),
                rules=[str(rule.get("rule", "")) for rule in (row.rules if row else [])],
                learned=row is not None,
                review_count=row.review_count if row else 0,
                available_reviews=len(reviews_for_type(session, question_type)),
                updated_at=row.updated_at or row.created_at if row else None,
            )
        )
    return TypeInstructionListResponse(instructions=entries)


@router.post("/{question_type}/refresh", response_model=TypeInstructionRefreshResponse)
def refresh(session: DbSession, question_type: QuestionType) -> TypeInstructionRefreshResponse:
    """Re-learn one type's instruction from its reviews. Requires a configured LLM."""
    try:
        row = refresh_type_instruction(
            session,
            question_type,
            base_instruction=base_type_instruction(question_type),
        )
    except Exception:
        session.rollback()
        raise

    if row is None:
        return TypeInstructionRefreshResponse(
            question_type=question_type,
            learned=False,
            rule_count=0,
            review_count=0,
            instruction=base_type_instruction(question_type),
        )
    return TypeInstructionRefreshResponse(
        question_type=question_type,
        learned=True,
        rule_count=len(row.rules),
        review_count=row.review_count,
        instruction=row.instruction,
    )
