"""Per-type instructions (ADR-033, ADR-063).

What is learned for a type (its active guidelines, ``tests/test_memory_guidelines.py``) is
rendered after the shipped instruction into the type slot, never appended after the prompt.
These check the slot and the shipped text.
"""

from __future__ import annotations

import book_documents as docs
import pytest
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType
from app.generation.prompts import base_type_instruction, build_prompt, render_taxonomy
from app.generation.spec import build_question_spec, require_approved_version
from app.ingestion import BookImportService
from app.memory import render_with_guidelines
from app.persistence.repositories import CurriculumRepository
from app.question_types import implemented_types

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


def test_rendering_keeps_the_shipped_text_first(session: Session) -> None:
    """The shipped text carries the format contract, which no review can teach."""
    rendered = render_with_guidelines("BASE CONTRACT", ["Be concise."])

    assert rendered.startswith("BASE CONTRACT")
    assert "- Be concise." in rendered
    assert render_with_guidelines("BASE CONTRACT", []) == "BASE CONTRACT"


@pytest.mark.parametrize("question_type", implemented_types())
def test_every_built_type_has_a_shipped_instruction(question_type: QuestionType) -> None:
    assert base_type_instruction(question_type)


def test_an_unbuilt_type_has_no_instruction_and_says_so() -> None:
    from app.errors import FeatureNotAvailableError
    from app.question_types import get_type

    unbuilt = [qt for qt in QuestionType if qt not in implemented_types()]
    for question_type in unbuilt:
        with pytest.raises(KeyError):
            get_type(question_type)
        with pytest.raises(FeatureNotAvailableError):
            base_type_instruction(question_type)
