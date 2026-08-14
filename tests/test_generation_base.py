"""Base question generation through a mocked structured LLM client."""

from __future__ import annotations

import book_documents as docs
from llm_fakes import MetricJudgeClient, SequencedDraftClient
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import ClaimViolation, Difficulty, QuestionKind, QuestionType
from app.generation.attempts import MAX_GENERATION_ATTEMPTS
from app.generation.base import DESCRIPTOR, BaseQuestionGenerator
from app.generation.schemas import RESPONSE_MODEL_FOR, DebuggingDraft
from app.generation.service import GenerationService
from app.generation.spec import build_question_spec
from app.ingestion import BookImportService, SourceRetrieval
from app.persistence.repositories import QuestionRepository

TAXONOMY = (
    b'{"schema_version":"1","label":"Python","topics":['
    b'{"name":"Strings","subtopics":[{"name":"Immutability"},{"name":"Slicing"}]},'
    b'{"name":"Loops","subtopics":[{"name":"While loops"}]}]}'
)


def _seed(session: Session, settings) -> tuple[object, object, object, list[int]]:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.think_python())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json", data=TAXONOMY
    )
    session.commit()
    return (
        version,
        version.topics[0],
        version.topics[0].subtopics[0],
        [section.id for chapter in book.chapters for section in chapter.sections],
    )


def _debugging_draft(topic_id: int, subtopic_ids: list[int]) -> DebuggingDraft:
    """A draft that passes deterministic validation.

    The reference solution has to be runnable Python that satisfies its own
    tests: since ADR-032 a failed check triggers a retry, so a fixture with a
    prose 'solution' would make every test spend three generation calls.
    """
    return DebuggingDraft(
        topic_id=topic_id,
        subtopic_ids=subtopic_ids,
        prompt="Find the bug.",
        code="s = 'ab'\ns[0] = 'c'",
        reference_solution="def fixed(s):\n    return 'c' + s[1:]",
        tests=[{"assert": "assert fixed('ab') == 'cb'"}],
        explanation="Item assignment on str fails.",
    )


def test_base_descriptor_unchanged() -> None:
    assert DESCRIPTOR.name == "base" and DESCRIPTOR.version == "1"
    assert DESCRIPTOR.label() == "base:base@1"


def test_base_generator_attaches_source_and_scoring_kind(session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))

    question = BaseQuestionGenerator(
        client=client, retrieval=SourceRetrieval(session)
    ).generate_one(spec, version=version)

    assert question.kind is QuestionKind.TESTABLE_PROGRAM
    assert question.question_type is QuestionType.DEBUGGING
    assert question.generator_name == "base"
    assert question.generator_version == "1"
    assert question.content is not None
    assert question.content["sources"][0]["section_id"] == section_ids[0]
    assert question.tests and "assert fixed('ab') == 'cb'" in question.tests
    call = client.generation_calls[0]
    assert call["model"] is RESPONSE_MODEL_FOR[QuestionType.DEBUGGING]
    assert "section text" in call["prompt"].lower()


def test_generation_prompt_carries_the_whole_taxonomy(session, settings) -> None:
    """The generator classifies its own question, so it needs every option."""
    version, topic, subtopic, section_ids = _seed(session, settings)
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))

    BaseQuestionGenerator(client=client, retrieval=SourceRetrieval(session)).generate_one(
        spec, version=version
    )

    prompt = client.generation_calls[0]["prompt"]
    assert "Immutability" in prompt
    assert "While loops" in prompt
    assert "Slicing" in prompt


def test_generator_claim_becomes_the_questions_taxonomy(session, settings) -> None:
    version, topic, _, section_ids = _seed(session, settings)
    both = [subtopic.id for subtopic in topic.subtopics]
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = MetricJudgeClient(draft=_debugging_draft(topic.id, both))

    question = BaseQuestionGenerator(
        client=client, retrieval=SourceRetrieval(session)
    ).generate_one(spec, version=version)

    assert question.topic_id == topic.id
    assert question.subtopic_ids == both


def test_a_subtopic_outside_the_claimed_topic_is_retried_then_kept(session, settings) -> None:
    """A cross-topic claim costs the retries and still yields a question (ADR-032).

    It used to raise, which discarded the whole batch. Now the violation is put
    back to the model, and after the cap the question is returned with its refused
    claim recorded -- the run continues and the miss stays visible.
    """
    version, topic, subtopic, section_ids = _seed(session, settings)
    other_topic_subtopic = version.topics[1].subtopics[0].id
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = MetricJudgeClient(
        draft=_debugging_draft(topic.id, [subtopic.id, other_topic_subtopic])
    )

    question = BaseQuestionGenerator(
        client=client, retrieval=SourceRetrieval(session)
    ).generate_one(spec, version=version)

    assert len(question.generation_attempts) == MAX_GENERATION_ATTEMPTS
    assert not any(attempt.accepted for attempt in question.generation_attempts)
    assert question.generation_attempts[-1].violations == [ClaimViolation.FOREIGN_SUBTOPICS]
    # Both ids exist, so both were stored; the deterministic checks refuse the
    # pairing rather than the row being unrepresentable.
    assert question.topic_id == topic.id
    assert question.subtopic_ids == [subtopic.id, other_topic_subtopic]


def test_the_second_attempt_is_told_which_id_to_change(session, settings) -> None:
    """Naming the fault is not enough; the retry must name the id and the fix.

    A live model, told only that "subtopic 106 is not under topic 11", returned
    the same id three times. So the correction says which id to remove -- and
    offers the other resolution, since a model that keeps naming a subtopic may
    be right about it and wrong about the topic.
    """
    version, topic, subtopic, section_ids = _seed(session, settings)
    other_topic_subtopic = version.topics[1].subtopics[0].id
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = MetricJudgeClient(
        draft=_debugging_draft(topic.id, [subtopic.id, other_topic_subtopic])
    )

    BaseQuestionGenerator(client=client, retrieval=SourceRetrieval(session)).generate_one(
        spec, version=version
    )

    first, second = client.generation_calls[0]["prompt"], client.generation_calls[1]["prompt"]
    assert "correction" not in first
    # The offending id, an instruction to remove it, and the topic that owns it.
    assert f"Either remove {other_topic_subtopic} from subtopic_ids" in second
    assert f"Subtopic {other_topic_subtopic}" in second
    assert f"set topic_id to {version.topics[1].id}" in second
    assert version.topics[1].name in second


def test_a_refused_claim_is_accepted_once_corrected(session, settings) -> None:
    """The retry is what makes a recoverable miss cost one extra call, not a run."""
    version, topic, subtopic, section_ids = _seed(session, settings)
    other_topic_subtopic = version.topics[1].subtopics[0].id
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_ids[0]],
    )
    client = SequencedDraftClient(
        drafts=[
            _debugging_draft(topic.id, [subtopic.id, other_topic_subtopic]),
            _debugging_draft(topic.id, [subtopic.id]),
        ]
    )

    question = BaseQuestionGenerator(
        client=client, retrieval=SourceRetrieval(session)
    ).generate_one(spec, version=version)

    assert len(question.generation_attempts) == 2
    assert [attempt.accepted for attempt in question.generation_attempts] == [False, True]
    assert question.subtopic_ids == [subtopic.id]


def test_base_generator_generates_one_unpersisted_question_per_section(
    session: Session, settings
) -> None:
    from app.generation import GenerationRequest

    version, topic, subtopic, section_ids = _seed(session, settings)
    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))

    questions = BaseQuestionGenerator(session=session, client=client).generate(
        GenerationRequest(
            curriculum_version_id=version.id,
            question_type=QuestionType.DEBUGGING,
            source_section_ids=section_ids[:2],
            difficulty=Difficulty.MEDIUM,
            count=1,
        )
    )

    assert len(questions) == 2
    assert [question.topic_id for question in questions] == [topic.id, topic.id]
    assert [question.subtopic_ids for question in questions] == [[subtopic.id], [subtopic.id]]
    assert all(question.id is None for question in questions)
    assert len(client.generation_calls) == 2


def test_service_persists_one_question_per_selected_section(session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))
    service = GenerationService(session, client=client)

    rows = service.generate_for_sections(
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.EASY,
        source_section_ids=section_ids[:2],
    )

    assert len(rows) == 2
    assert QuestionRepository(session).count() == 2
    assert [row.topic_id for row in rows] == [topic.id, topic.id]
    assert [list(row.subtopic_ids) for row in rows] == [[subtopic.id], [subtopic.id]]
    assert all(row.question_type is QuestionType.DEBUGGING for row in rows)
    assert all(row.spec and row.spec["source_section_ids"] for row in rows)
    assert len(client.generation_calls) == 2
