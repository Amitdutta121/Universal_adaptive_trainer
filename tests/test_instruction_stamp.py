"""Recording which instruction wrote each question (ADR-040).

There is one generator, so ``base@1`` distinguishes nothing. What differs
between two questions is the instruction the generator followed, and these check
that the instruction is named on the question, is the text actually sent, and
does not move when the instruction is later relearned.
"""

from __future__ import annotations

import book_documents as docs
import pytest
from llm_fakes import metric_results
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, JudgeGate, QuestionStatus, QuestionType
from app.evaluation import PedagogicalEvaluation
from app.evaluation.schema import PedagogicalEvalStatus
from app.generation.base import BaseQuestionGenerator
from app.generation.prompts import base_type_instruction, instruction_fingerprint
from app.ingestion import BookImportService
from app.persistence.models import QuestionRow
from app.persistence.repositories import (
    QuestionRepository,
    TypeInstructionRepository,
)
from app.web.routes.api.schemas import InstructionStamp, QuestionSummary

TAXONOMY = (
    b'{"schema_version":"1","label":"Python","topics":['
    b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
)


def _seed(session: Session, settings) -> None:
    BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    TaxonomyImportService(session, settings).import_upload(filename="tax.json", data=TAXONOMY)
    session.commit()


def _stamp(session: Session, question_type: QuestionType) -> dict:
    """The stamp the generator would write for this type right now."""
    _instruction, stamp = BaseQuestionGenerator(session=session)._type_instruction(question_type)
    return stamp["type_instruction"]


# --------------------------------------------------------------- the fingerprint


def test_the_same_text_always_names_the_same_instruction() -> None:
    assert instruction_fingerprint("Write a question.") == instruction_fingerprint(
        "Write a question."
    )


def test_a_changed_instruction_gets_a_different_name() -> None:
    assert instruction_fingerprint("Write a question.") != instruction_fingerprint(
        "Write a question. Keep options short."
    )


# ------------------------------------------------------------------- the stamp


def test_an_unlearned_type_is_stamped_shipped(session: Session) -> None:
    stamp = _stamp(session, QuestionType.MULTIPLE_CHOICE)

    assert stamp["source"] == "shipped"
    assert stamp["rule_count"] == 0
    assert stamp["fingerprint"] == instruction_fingerprint(
        base_type_instruction(QuestionType.MULTIPLE_CHOICE)
    )


def test_a_learned_type_is_stamped_learned(session: Session) -> None:
    TypeInstructionRepository(session).upsert(
        QuestionType.MULTIPLE_CHOICE,
        instruction="BASE\n\nThis professor additionally requires:\n- Keep options short.",
        rules=[{"rule": "Keep options short.", "review_ids": [1]}],
        review_count=4,
    )
    session.commit()

    stamp = _stamp(session, QuestionType.MULTIPLE_CHOICE)

    assert stamp["source"] == "learned"
    assert stamp["rule_count"] == 1
    assert stamp["review_count"] == 4
    assert stamp["fingerprint"] != instruction_fingerprint(
        base_type_instruction(QuestionType.MULTIPLE_CHOICE)
    )


def test_relearning_changes_the_name(session: Session) -> None:
    """Two questions written from different instructions must not look alike."""
    repository = TypeInstructionRepository(session)
    repository.upsert(
        QuestionType.MULTIPLE_CHOICE, instruction="ONE", rules=[{"rule": "a"}], review_count=1
    )
    session.commit()
    before = _stamp(session, QuestionType.MULTIPLE_CHOICE)["fingerprint"]

    repository.upsert(
        QuestionType.MULTIPLE_CHOICE, instruction="TWO", rules=[{"rule": "b"}], review_count=2
    )
    session.commit()

    assert _stamp(session, QuestionType.MULTIPLE_CHOICE)["fingerprint"] != before


def test_the_stamp_names_the_text_that_is_sent(session: Session) -> None:
    """Not the row: what the model read is the only honest provenance."""
    TypeInstructionRepository(session).upsert(
        QuestionType.CODING, instruction="EXACT TEXT SENT", rules=[], review_count=3
    )
    session.commit()

    instruction, stamp = BaseQuestionGenerator(session=session)._type_instruction(
        QuestionType.CODING
    )

    assert instruction == "EXACT TEXT SENT"
    assert stamp["type_instruction"]["fingerprint"] == instruction_fingerprint("EXACT TEXT SENT")


# ------------------------------------------------------- what reaches the client


def _question(session: Session, context: dict | None) -> QuestionRow:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Which statement is true?",
            original_prompt="Which statement is true?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            status=QuestionStatus.VALIDATION_PASSED,
            personalization_context=context,
            pedagogical_eval=PedagogicalEvaluation(
                status=PedagogicalEvalStatus.COMPLETED,
                gate=JudgeGate.APPROVED,
                metrics=metric_results(),
                judge_model="fake/judge",
            ).model_dump(mode="json"),
        )
    )
    session.commit()
    return row


def test_the_api_publishes_the_stamp(session: Session) -> None:
    row = _question(
        session,
        {
            "type_instruction": {
                "source": "learned",
                "fingerprint": "abcd1234",
                "rule_count": 2,
                "review_count": 7,
            }
        },
    )

    summary = QuestionSummary.from_row(row)

    assert summary.instruction is not None
    assert summary.instruction.source == "learned"
    assert summary.instruction.fingerprint == "abcd1234"
    assert summary.instruction.rule_count == 2


def test_a_question_from_before_the_stamp_reports_nothing(session: Session) -> None:
    """Absent is not 'shipped'; claiming either would be an invention."""
    row = _question(session, None)

    assert QuestionSummary.from_row(row).instruction is None


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"type_instruction": "not a dict"}, {"type_instruction": {"source": "guessed"}}],
)
def test_an_unreadable_stamp_is_reported_as_absent(payload: dict | None) -> None:
    assert InstructionStamp.from_context(payload) is None


def test_is_edited_reports_the_professor_edit_not_the_seeded_original(session: Session) -> None:
    """``original_prompt`` is seeded on every question, so it cannot be the test."""
    row = _question(session, None)

    assert QuestionSummary.from_row(row).is_edited is False

    row.prompt = "Which statement about immutability is true?"
    session.commit()

    assert QuestionSummary.from_row(row).is_edited is True
