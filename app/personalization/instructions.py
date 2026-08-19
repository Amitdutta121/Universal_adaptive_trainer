"""Learn the generation instruction for one question type from reviews (ADR-033).

Personalization is the type instruction itself, not a block appended after it.
The professor's reviews of questions of a given type are turned into rules, the
rules are rendered into the text that occupies the type-specific slot, and the
generator sees nothing else.

Rules **accumulate**. The rewriter is shown the rules it already has and returns
them edited, with new ones appended and obsolete ones dropped by name. Rewriting
the whole instruction from scratch each round was measured to lose earlier
lessons: over six rounds a rule earned in round three had to survive three more
rewrites to reach round six, and did not — the text drifted from "test a single
concept, not a collection of unrelated facts" to "avoid broad, unrelated
content", and specific rules about annotating defects and verifying a single
correct option disappeared entirely.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.domain.enums import QuestionType, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS, professor_edits
from app.errors import NotFoundError
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import ProfessorReviewRow, TypeInstructionRow
from app.persistence.repositories import ProfessorReviewRepository, TypeInstructionRepository

logger = logging.getLogger(__name__)

#: Reviews sent to the rewriter. Enough to show a pattern without paying for the
#: whole history on every refresh.
REVIEW_LIMIT = 60

#: Characters of a question kept when quoting it as evidence.
SNIPPET_CHARS = 240

SYSTEM = (
    "You maintain the instruction a question generator follows for ONE question type. "
    "You are given the rules already learned and the professor's reviews. Return the "
    "rules edited: keep the ones the evidence still supports, reword one that is vague, "
    "add one for a complaint not yet covered, and drop one the professor has stopped "
    "making. Every rule must be concrete enough to follow -- name what to do, not what "
    "to be. Ground each rule in the reviews given and cite their ids. Do not invent "
    "preferences the evidence does not support."
)


class LearnedRule(BaseModel):
    """One instruction the professor's reviews justify."""

    rule: str = Field(min_length=1, description="A concrete, imperative instruction.")
    review_ids: list[int] = Field(
        default_factory=list, description="Reviews that justify this rule."
    )


class LearnedRules(BaseModel):
    rules: list[LearnedRule] = Field(default_factory=list)


def render_instruction(base: str, rules: list[LearnedRule]) -> str:
    """Combine the shipped type instruction with the learned rules.

    The shipped text stays: it carries the format contract (what fields to fill,
    how the test harness runs) which is a fact about this application, not a
    preference anyone reviewed. The learned rules are appended as requirements.
    """
    if not rules:
        return base
    lines = [base, "", "This professor additionally requires:"]
    lines.extend(f"- {rule.rule}" for rule in rules)
    return "\n".join(lines)


def _serialize(reviews: list[ProfessorReviewRow]) -> str:
    """Describe each review as generation evidence.

    ``professor_corrected`` carries only the fields the professor actually
    changed. The edit form submits all three whether or not they moved, so
    quoting the edited prompt unconditionally would show a rewrite identical to
    the original and hide a professor who fixed only the tests.
    """
    entries = []
    for review in reviews:
        question = review.question
        original = question.original_prompt or question.prompt if question else None
        edits = (
            professor_edits(
                changed_fields=list(review.changed_fields or []),
                edited_prompt=review.edited_prompt,
                edited_reference_solution=review.edited_reference_solution,
                edited_tests=review.edited_tests,
                limit=SNIPPET_CHARS,
            )
            if review.decision is ReviewDecision.EDIT
            else {}
        )
        entries.append(
            {
                "review_id": review.id,
                "decision": str(review.decision),
                "reasons": [REJECTION_REASON_LABELS[reason] for reason in review.reasons],
                "comment": (review.comment or "").strip() or None,
                "question": (original or "")[:SNIPPET_CHARS] or None,
                "professor_corrected": edits or None,
            }
        )
    return json.dumps(entries, separators=(",", ":"))


def reviews_for_type(session: Session, question_type: QuestionType) -> list[ProfessorReviewRow]:
    """Reviews of questions of this type, newest first, capped at the limit."""
    reviews = ProfessorReviewRepository(session).list_with_questions(limit=500)
    matching = [
        review
        for review in reviews
        if review.question is not None and review.question.question_type is question_type
    ]
    return matching[:REVIEW_LIMIT]


def refresh_type_instruction(
    session: Session,
    question_type: QuestionType,
    *,
    base_instruction: str,
    client: StructuredLLMClient | None = None,
) -> TypeInstructionRow | None:
    """Re-learn one type's instruction from its reviews.

    Returns ``None`` when no review of this type exists yet, leaving the shipped
    instruction in place. A type nobody has reviewed has nothing to learn from,
    and inventing rules for it would be the opposite of personalization.
    """
    reviews = reviews_for_type(session, question_type)
    if not reviews:
        logger.info("No reviews for %s; instruction left unchanged.", question_type.value)
        return None

    repository = TypeInstructionRepository(session)
    existing = repository.get(question_type)
    current = [LearnedRule.model_validate(rule) for rule in (existing.rules if existing else [])]

    llm = client or get_structured_client()
    learned = llm.complete_structured(
        system=SYSTEM,
        prompt=(
            f"Question type: {question_type.value}\n\n"
            f"Rules already learned:\n{json.dumps([r.model_dump() for r in current], indent=2)}\n\n"
            f"The professor's reviews of questions of this type ({len(reviews)}):\n"
            f"{_serialize(reviews)}\n\n"
            "Return the edited rules."
        ),
        response_model=LearnedRules,
    )

    row = repository.upsert(
        question_type,
        instruction=render_instruction(base_instruction, learned.rules),
        rules=[rule.model_dump() for rule in learned.rules],
        review_count=len(reviews),
    )
    session.commit()
    logger.info(
        "Relearned %s from %s reviews: %s rules (was %s).",
        question_type.value,
        len(reviews),
        len(learned.rules),
        len(current),
    )
    return row


def delete_type_instruction_rule(
    session: Session,
    question_type: QuestionType,
    *,
    rule_index: int,
    base_instruction: str,
) -> TypeInstructionRow | None:
    """Delete one learned rule and re-render the stored instruction.

    Returns ``None`` when the deleted rule was the last one, which means the
    shipped instruction is back in force and the stored row can be dropped.
    """
    repository = TypeInstructionRepository(session)
    row = repository.get(question_type)
    if row is None:
        raise NotFoundError(
            f"The {question_type.value} type is already using its shipped instruction.",
            detail="There is no learned instruction row to edit.",
        )

    rules = [LearnedRule.model_validate(rule) for rule in row.rules]
    if rule_index < 0 or rule_index >= len(rules):
        raise NotFoundError(
            f"Rule {rule_index + 1} does not exist for {question_type.value}.",
            detail="Choose a learned rule that is still present.",
        )

    removed = rules.pop(rule_index)
    if not rules:
        repository.delete(question_type)
        session.commit()
        logger.info(
            "Deleted the last learned rule for %s (%s); reverted to shipped instruction.",
            question_type.value,
            removed.rule,
        )
        return None

    updated = repository.upsert(
        question_type,
        instruction=render_instruction(base_instruction, rules),
        rules=[rule.model_dump() for rule in rules],
        review_count=row.review_count,
    )
    session.commit()
    logger.info(
        "Deleted learned rule %s for %s; %s rule(s) remain.",
        removed.rule,
        question_type.value,
        len(rules),
    )
    return updated
