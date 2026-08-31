"""Regenerating an existing question with instructor feedback.

A regeneration is a NEW question grounded in the same section, type and
difficulty as the source, with the instructor's feedback threaded into the
generation prompt. The source row is never touched, no review is written, and no
instruction relearn is triggered.
"""

from __future__ import annotations

import pytest
from llm_fakes import MetricJudgeClient, SequencedDraftClient
from test_generation_base import _debugging_draft, _seed

from app.domain.enums import CurriculumStatus, Difficulty, QuestionType
from app.errors import InvalidQuestionSpecError
from app.generation.service import GenerationService
from app.persistence.models import CurriculumVersionRow
from app.persistence.repositories import (
    ProfessorReviewRepository,
    TypeInstructionRepository,
)


def _generate_source(session, settings, client):
    version, topic, subtopic, section_ids = _seed(session, settings)
    rows = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    return version, topic, subtopic, section_ids, rows[0]


def test_regenerate_creates_new_row_and_leaves_source_untouched(session, settings) -> None:
    client = MetricJudgeClient(draft=_debugging_draft(1, [1]))
    _version, _topic, _subtopic, _sections, source = _generate_source(session, settings, client)

    source_id = source.id
    source_prompt = source.prompt
    source_status = source.status
    source_original_prompt = source.original_prompt
    source_sections = source.spec["source_section_ids"]

    new_row = GenerationService(session, client=client).regenerate_from_question(
        source_id, feedback="Focus on list slicing, not indexing."
    )

    assert new_row.id != source_id
    assert new_row.regenerated_from_question_id == source_id
    assert new_row.regeneration_feedback == "Focus on list slicing, not indexing."
    assert new_row.question_type is QuestionType.DEBUGGING
    assert new_row.difficulty is Difficulty.MEDIUM
    assert new_row.spec["source_section_ids"] == source_sections

    session.refresh(source)
    assert source.prompt == source_prompt
    assert source.status == source_status
    assert source.original_prompt == source_original_prompt
    assert source.regenerated_from_question_id is None
    assert list(source.reviews) == []


def test_regenerate_prompt_carries_the_feedback_block(session, settings) -> None:
    client = MetricJudgeClient(draft=_debugging_draft(1, [1]))
    _version, topic, subtopic, _sections, source = _generate_source(session, settings, client)

    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))
    GenerationService(session, client=client).regenerate_from_question(
        source.id, feedback="Make the distractors plausible misconceptions."
    )

    prompt = client.generation_calls[-1]["prompt"]
    assert prompt.count("--- instructor feedback ---") == 1
    assert "Make the distractors plausible misconceptions." in prompt


def test_regenerate_writes_no_review_and_no_instruction_relearn(session, settings) -> None:
    client = MetricJudgeClient(draft=_debugging_draft(1, [1]))
    _version, topic, subtopic, _sections, source = _generate_source(session, settings, client)

    reviews_before = ProfessorReviewRepository(session).count()
    instruction_before = TypeInstructionRepository(session).get(QuestionType.DEBUGGING)

    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))
    GenerationService(session, client=client).regenerate_from_question(
        source.id, feedback="Too easy — raise the difficulty of the reasoning."
    )

    assert ProfessorReviewRepository(session).count() == reviews_before
    assert TypeInstructionRepository(session).get(QuestionType.DEBUGGING) == instruction_before


def test_regenerate_is_refused_when_the_source_curriculum_is_superseded(session, settings) -> None:
    client = MetricJudgeClient(draft=_debugging_draft(1, [1]))
    _version, _topic, _subtopic, _sections, source = _generate_source(session, settings, client)

    # The source question's curriculum is no longer the approved one.
    version_row = session.get(CurriculumVersionRow, source.curriculum_version_id)
    version_row.status = CurriculumStatus.SUPERSEDED
    session.commit()

    with pytest.raises(InvalidQuestionSpecError):
        GenerationService(session, client=client).regenerate_from_question(
            source.id, feedback="anything"
        )


def test_regenerate_recovers_the_section_from_content_when_spec_is_missing(
    session, settings
) -> None:
    client = MetricJudgeClient(draft=_debugging_draft(1, [1]))
    _version, topic, subtopic, _sections, source = _generate_source(session, settings, client)

    # Simulate a row written before specs were stored: keep content["sources"].
    source.spec = None
    session.commit()

    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))
    new_row = GenerationService(session, client=client).regenerate_from_question(
        source.id, feedback="Ground it more tightly in the section."
    )

    assert new_row.spec["source_section_ids"] == [source.content["sources"][0]["section_id"]]


def test_regenerate_survives_a_correction_retry_keeping_the_feedback_block(
    session, settings
) -> None:
    client = MetricJudgeClient(draft=_debugging_draft(1, [1]))
    version, topic, subtopic, _sections, source = _generate_source(session, settings, client)

    other_topic_subtopic = version.topics[1].subtopics[0].id
    client = SequencedDraftClient(
        drafts=[
            _debugging_draft(topic.id, [subtopic.id, other_topic_subtopic]),
            _debugging_draft(topic.id, [subtopic.id]),
        ]
    )
    GenerationService(session, client=client).regenerate_from_question(
        source.id, feedback="Keep the bug subtle."
    )

    second = client.generation_calls[1]["prompt"]
    assert "--- instructor feedback ---" in second
    assert "--- correction ---" in second
