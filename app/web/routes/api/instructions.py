"""Per-type generation instructions learned from professor reviews (ADR-033).

Reading them is free. Refreshing one costs a model call, so it is a POST the
professor triggers rather than something that happens behind a review.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.domain.enums import QuestionType
from app.errors import NotFoundError
from app.generation.prompts import base_type_instruction
from app.persistence.models import TypeInstructionRow
from app.persistence.repositories import TypeInstructionRepository
from app.personalization import (
    delete_type_instruction_rule,
    refresh_type_instruction,
    reviews_for_type,
)
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    TypeInstructionListResponse,
    TypeInstructionOut,
    TypeInstructionRefreshResponse,
)

router = APIRouter(prefix="/instructions", tags=["instructions"])


def _out(
    session: DbSession,
    question_type: QuestionType,
    *,
    row: TypeInstructionRow | None = None,
    instruction_text: str | None = None,
) -> TypeInstructionOut:
    return TypeInstructionOut(
        question_type=question_type,
        instruction=instruction_text
        or (row.instruction if row else base_type_instruction(question_type)),
        rules=[str(rule.get("rule", "")) for rule in (row.rules if row else [])],
        learned=row is not None,
        review_count=row.review_count if row else 0,
        available_reviews=len(reviews_for_type(session, question_type)),
        updated_at=row.updated_at or row.created_at if row else None,
    )


@router.get("", response_model=TypeInstructionListResponse)
def list_instructions(session: DbSession) -> TypeInstructionListResponse:
    """Every question type, with whatever has been learned for it.

    Types with nothing learned are listed too, carrying the shipped instruction
    and a review count -- that is how a professor sees which types have enough
    feedback to be worth refreshing.
    """
    stored = {row.question_type: row for row in TypeInstructionRepository(session).list_all()}
    return TypeInstructionListResponse(
        instructions=[
            _out(session, question_type, row=stored.get(question_type))
            for question_type in QuestionType
        ]
    )


@router.delete("/{question_type}", response_model=TypeInstructionOut)
def delete_instruction(session: DbSession, question_type: QuestionType) -> TypeInstructionOut:
    """Delete one learned row so this type falls back to its shipped instruction."""
    repository = TypeInstructionRepository(session)
    if not repository.delete(question_type):
        raise NotFoundError(
            f"The {question_type.value} type is already using its shipped instruction.",
            detail="There is no learned instruction row to delete.",
        )
    session.commit()
    return _out(
        session,
        question_type,
        instruction_text=base_type_instruction(question_type),
    )


@router.delete("/{question_type}/rules/{rule_index}", response_model=TypeInstructionOut)
def delete_rule(
    session: DbSession,
    question_type: QuestionType,
    rule_index: int,
) -> TypeInstructionOut:
    """Delete one learned rule and re-render the instruction from what remains."""
    try:
        row = delete_type_instruction_rule(
            session,
            question_type,
            rule_index=rule_index,
            base_instruction=base_type_instruction(question_type),
        )
    except Exception:
        session.rollback()
        raise

    if row is None:
        return _out(
            session,
            question_type,
            instruction_text=base_type_instruction(question_type),
        )
    return _out(session, question_type, row=row)


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
