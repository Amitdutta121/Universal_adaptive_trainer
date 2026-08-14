"""Per-type learned instructions (ADR-033).

Personalization is the type instruction itself, so these check three things: it
is only learned from real reviews, it reaches the generator's prompt, and rules
accumulate rather than being rewritten away.
"""

from __future__ import annotations

from typing import Any

import book_documents as docs
import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType, RejectionReason, ReviewDecision
from app.feedback import submit_review
from app.generation.prompts import base_type_instruction, build_prompt, render_taxonomy
from app.generation.spec import build_question_spec, require_approved_version
from app.ingestion import BookImportService
from app.persistence.models import QuestionRow
from app.persistence.repositories import (
    CurriculumRepository,
    QuestionRepository,
    TypeInstructionRepository,
)
from app.personalization import LearnedRule, LearnedRules, refresh_type_instruction
from app.personalization.instructions import render_instruction

TAXONOMY = (
    b'{"schema_version":"1","label":"Python","topics":['
    b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
)


class RewriterClient:
    """Returns a fixed rule set, and records what it was shown."""

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self.rules = rules
        self.prompts: list[str] = []

    @property
    def description(self) -> str:
        return "fake/rewriter"

    def complete_structured(self, *, system: str, prompt: str, response_model: type[BaseModel]):
        self.prompts.append(prompt)
        return LearnedRules(rules=[LearnedRule(**rule) for rule in self.rules])


def _seed(session: Session, settings) -> None:
    BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    TaxonomyImportService(session, settings).import_upload(filename="tax.json", data=TAXONOMY)
    session.commit()


def _reviewed_question(session: Session, *, comment: str) -> QuestionRow:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Which of the following is true about strings?",
            original_prompt="Which of the following is true about strings?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.MEDIUM,
        )
    )
    session.commit()
    submit_review(
        session,
        question_id=row.id,
        decision=ReviewDecision.EDIT,
        comment=comment,
        prompt="Which statement about string immutability is true?",
        reference_solution="",
        tests="",
    )
    session.commit()
    return row


def test_a_type_with_no_reviews_learns_nothing(session: Session, settings) -> None:
    """Inventing rules from no evidence would be the opposite of personalization."""
    client = RewriterClient([{"rule": "Should never be reached.", "review_ids": []}])

    row = refresh_type_instruction(
        session,
        QuestionType.MULTIPLE_CHOICE,
        base_instruction="BASE",
        client=client,
    )

    assert row is None
    assert client.prompts == []
    assert TypeInstructionRepository(session).get(QuestionType.MULTIPLE_CHOICE) is None


def test_reviews_of_this_type_become_rules(session: Session, settings) -> None:
    _seed(session, settings)
    _reviewed_question(session, comment="The options carry too much explanatory text.")
    client = RewriterClient([{"rule": "Keep every option under ten words.", "review_ids": [1]}])

    row = refresh_type_instruction(
        session,
        QuestionType.MULTIPLE_CHOICE,
        base_instruction="BASE",
        client=client,
    )

    assert row is not None
    assert row.review_count == 1
    assert [rule["rule"] for rule in row.rules] == ["Keep every option under ten words."]
    assert "BASE" in row.instruction
    assert "Keep every option under ten words." in row.instruction
    # The professor's own words reach the rewriter, not just the decision.
    assert "too much explanatory text" in client.prompts[0]


def test_only_reviews_of_the_same_type_are_used(session: Session, settings) -> None:
    _seed(session, settings)
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Debug this.",
            original_prompt="Debug this.",
            question_type=QuestionType.DEBUGGING,
            difficulty=Difficulty.MEDIUM,
        )
    )
    session.commit()
    submit_review(
        session,
        question_id=row.id,
        decision=ReviewDecision.REJECT,
        comment="Broken.",
        reasons=[RejectionReason.TECHNICALLY_INCORRECT],
    )
    session.commit()
    client = RewriterClient([{"rule": "Anything.", "review_ids": []}])

    assert (
        refresh_type_instruction(
            session, QuestionType.MULTIPLE_CHOICE, base_instruction="BASE", client=client
        )
        is None
    )
    assert (
        refresh_type_instruction(
            session, QuestionType.DEBUGGING, base_instruction="BASE", client=client
        )
        is not None
    )


def test_the_rewriter_is_shown_the_rules_it_already_has(session: Session, settings) -> None:
    """Rules accumulate. Rewriting from scratch each round loses earlier lessons."""
    _seed(session, settings)
    _reviewed_question(session, comment="Too wordy.")
    first = RewriterClient([{"rule": "Keep options short.", "review_ids": [1]}])
    refresh_type_instruction(
        session, QuestionType.MULTIPLE_CHOICE, base_instruction="BASE", client=first
    )

    second = RewriterClient(
        [
            {"rule": "Keep options short.", "review_ids": [1]},
            {"rule": "Never annotate the defect being tested.", "review_ids": [2]},
        ]
    )
    row = refresh_type_instruction(
        session, QuestionType.MULTIPLE_CHOICE, base_instruction="BASE", client=second
    )

    assert "Keep options short." in second.prompts[0]
    assert len(row.rules) == 2
    assert "Never annotate the defect being tested." in row.instruction


def test_the_learned_instruction_replaces_the_shipped_one_in_the_prompt(
    session: Session, settings
) -> None:
    """It occupies the type slot; it is not appended after the prompt."""
    _seed(session, settings)
    approved = CurriculumRepository(session).get_approved()
    assert approved is not None
    version = require_approved_version(session, approved.id)
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[1],
    )

    _system, prompt = build_prompt(
        spec,
        section_text="Some text.",
        citation="Book, Page 1",
        taxonomy=render_taxonomy(version),
        type_instruction="LEARNED INSTRUCTION",
    )

    assert "LEARNED INSTRUCTION" in prompt
    assert base_type_instruction(QuestionType.MULTIPLE_CHOICE) not in prompt


def test_render_instruction_keeps_the_shipped_text(session: Session) -> None:
    """The shipped text carries the format contract, which no review can teach."""
    rendered = render_instruction("BASE CONTRACT", [LearnedRule(rule="Be concise.")])

    assert rendered.startswith("BASE CONTRACT")
    assert "- Be concise." in rendered
    assert render_instruction("BASE CONTRACT", []) == "BASE CONTRACT"


@pytest.mark.parametrize("question_type", list(QuestionType))
def test_every_type_has_a_shipped_instruction(question_type: QuestionType) -> None:
    assert base_type_instruction(question_type)
