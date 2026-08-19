"""Per-chunk batch generation: the compiler, the service, and the two endpoints.

The compiler is tested on its own because it is the one rule the console is not
allowed to restate (ADR-044): how many questions a chunk produces, and which
format each of them gets.
"""

from __future__ import annotations

import book_documents as docs
import pytest
from llm_fakes import MetricJudgeClient
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType
from app.errors import InvalidQuestionSpecError
from app.generation.batch import (
    ChunkQuestionRequest,
    compile_chunk_requests,
    count_identical_requests,
)
from app.generation.schemas import DebuggingDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.repositories import QuestionRepository

TAXONOMY = (
    b'{"schema_version":"1","label":"Python","topics":['
    b'{"name":"Loops","subtopics":[{"name":"While loops"}]}]}'
)


def _seed(session: Session, settings) -> tuple[object, object, list[int]]:
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
        [section.id for chapter in book.chapters for section in chapter.sections],
    )


def _draft(topic_id: int, subtopic_ids: list[int]) -> DebuggingDraft:
    """A draft that passes deterministic validation, so no retry is spent."""
    return DebuggingDraft(
        topic_id=topic_id,
        subtopic_ids=subtopic_ids,
        prompt="Find the bug.",
        code="s = 'ab'\ns[0] = 'c'",
        reference_solution="def fixed(s):\n    return 'c' + s[1:]",
        tests=[{"assert": "assert fixed('ab') == 'cb'"}],
        explanation="Item assignment on str fails.",
    )


def _chunk(
    section_id: int,
    *,
    easy: int = 0,
    medium: int = 0,
    hard: int = 0,
    types: list[QuestionType] | None = None,
) -> ChunkQuestionRequest:
    return ChunkQuestionRequest(
        section_id=section_id,
        counts={Difficulty.EASY: easy, Difficulty.MEDIUM: medium, Difficulty.HARD: hard},
        question_types=tuple([QuestionType.DEBUGGING] if types is None else types),
    )


# --- the compiler -----------------------------------------------------------


def test_counts_expand_into_one_planned_question_each() -> None:
    planned = compile_chunk_requests([_chunk(1, easy=2, hard=1)])

    assert [question.difficulty for question in planned] == [
        Difficulty.EASY,
        Difficulty.EASY,
        Difficulty.HARD,
    ]
    assert all(question.section_id == 1 for question in planned)


def test_difficulties_are_walked_in_a_fixed_order() -> None:
    planned = compile_chunk_requests([_chunk(1, hard=1, easy=1, medium=1)])

    assert [question.difficulty for question in planned] == [
        Difficulty.EASY,
        Difficulty.MEDIUM,
        Difficulty.HARD,
    ]


def test_every_count_is_made_in_every_chosen_format() -> None:
    """One easy and one medium with two formats is four questions, not two."""
    planned = compile_chunk_requests(
        [_chunk(1, easy=1, medium=1, types=[QuestionType.CODING, QuestionType.DEBUGGING])]
    )

    assert [(question.difficulty, question.question_type) for question in planned] == [
        (Difficulty.EASY, QuestionType.CODING),
        (Difficulty.EASY, QuestionType.DEBUGGING),
        (Difficulty.MEDIUM, QuestionType.CODING),
        (Difficulty.MEDIUM, QuestionType.DEBUGGING),
    ]


def test_choosing_three_formats_triples_the_count() -> None:
    planned = compile_chunk_requests(
        [
            _chunk(
                1,
                medium=2,
                types=[QuestionType.CODING, QuestionType.DEBUGGING, QuestionType.PARSONS],
            )
        ]
    )

    assert len(planned) == 6
    assert all(question.difficulty is Difficulty.MEDIUM for question in planned)


def test_one_of_each_difficulty_in_two_formats_is_six_questions() -> None:
    """The professor's own example: MCQ and Parsons, one of each difficulty."""
    planned = compile_chunk_requests(
        [
            _chunk(
                1,
                easy=1,
                medium=1,
                hard=1,
                types=[QuestionType.MULTIPLE_CHOICE, QuestionType.PARSONS],
            )
        ]
    )

    assert len(planned) == 6
    assert sum(1 for q in planned if q.question_type is QuestionType.PARSONS) == 3
    assert sum(1 for q in planned if q.difficulty is Difficulty.HARD) == 2


def test_chunks_keep_their_submitted_order() -> None:
    planned = compile_chunk_requests([_chunk(7, easy=1), _chunk(3, easy=1)])

    assert [question.section_id for question in planned] == [7, 3]


def test_a_chunk_asking_for_nothing_is_skipped_not_refused() -> None:
    planned = compile_chunk_requests([_chunk(1, easy=1), _chunk(2)])

    assert [question.section_id for question in planned] == [1]


def test_an_empty_sheet_is_refused() -> None:
    with pytest.raises(InvalidQuestionSpecError):
        compile_chunk_requests([])


def test_a_sheet_of_zeroes_is_refused() -> None:
    with pytest.raises(InvalidQuestionSpecError):
        compile_chunk_requests([_chunk(1), _chunk(2)])


def test_counts_without_a_format_are_refused() -> None:
    with pytest.raises(InvalidQuestionSpecError):
        compile_chunk_requests([_chunk(1, easy=1, types=[])])


def test_repeats_are_counted_not_refused() -> None:
    planned = compile_chunk_requests([_chunk(1, medium=3, types=[QuestionType.CODING])])

    assert len(planned) == 3
    # Three identical requests: the first is the question, two repeat it.
    assert count_identical_requests(planned) == 2


def test_a_second_format_does_not_reduce_the_repeats() -> None:
    """A repeat now comes only from a count above one, never from the format list."""
    planned = compile_chunk_requests(
        [_chunk(1, medium=2, types=[QuestionType.CODING, QuestionType.DEBUGGING])]
    )

    # Two coding and two debugging: one repeat within each format.
    assert len(planned) == 4
    assert count_identical_requests(planned) == 2


# --- the service ------------------------------------------------------------


def test_service_generates_every_planned_question(session, settings) -> None:
    version, topic, section_ids = _seed(session, settings)
    client = MetricJudgeClient(draft=_draft(topic.id, [topic.subtopics[0].id]))

    rows = GenerationService(session, client=client).generate_batch(
        curriculum_version_id=version.id,
        chunks=[
            _chunk(section_ids[0], easy=1, medium=1),
            _chunk(section_ids[1], hard=2),
        ],
    )

    # One format each, so the counts are the totals: 1 + 1, then 2.
    assert len(rows) == 4
    assert QuestionRepository(session).count() == 4
    assert [row.difficulty for row in rows] == [
        Difficulty.EASY,
        Difficulty.MEDIUM,
        Difficulty.HARD,
        Difficulty.HARD,
    ]
    assert [row.spec["source_section_ids"] for row in rows] == [
        [section_ids[0]],
        [section_ids[0]],
        [section_ids[1]],
        [section_ids[1]],
    ]
    assert len(client.generation_calls) == 4


def test_service_refuses_a_sheet_that_asks_for_nothing(session, settings) -> None:
    version, topic, section_ids = _seed(session, settings)
    client = MetricJudgeClient(draft=_draft(topic.id, [topic.subtopics[0].id]))

    with pytest.raises(InvalidQuestionSpecError):
        GenerationService(session, client=client).generate_batch(
            curriculum_version_id=version.id, chunks=[_chunk(section_ids[0])]
        )

    assert QuestionRepository(session).count() == 0
    assert client.generation_calls == []


# --- the endpoints ----------------------------------------------------------


def test_batch_plan_prices_a_sheet_without_generating(client) -> None:
    response = client.post(
        "/api/questions/batch-plan",
        json={
            "chunks": [
                {
                    "section_id": 1,
                    "easy": 1,
                    "hard": 2,
                    "question_types": ["coding", "debugging"],
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    # (1 easy + 2 hard) in each of two formats.
    assert body["totals"]["questions_to_create"] == 6
    assert body["totals"]["generation_calls"] == 6
    assert body["totals"]["judge_calls"] == 24
    assert body["totals"]["easy"] == 2
    assert body["totals"]["hard"] == 4
    assert body["totals"]["identical_repeats"] == 2
    assert [question["question_type"] for question in body["planned"]][:2] == [
        "coding",
        "debugging",
    ]


def test_batch_plan_reports_identical_repeats(client) -> None:
    response = client.post(
        "/api/questions/batch-plan",
        json={"chunks": [{"section_id": 1, "medium": 3, "question_types": ["coding"]}]},
    )

    assert response.json()["totals"]["identical_repeats"] == 2


def test_batch_plan_refuses_a_sheet_with_no_chunks(client) -> None:
    """Refused by the request schema, before the compiler is reached."""
    response = client.post("/api/questions/batch-plan", json={"chunks": []})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_batch_plan_refuses_counts_without_a_format(client) -> None:
    response = client.post(
        "/api/questions/batch-plan",
        json={"chunks": [{"section_id": 1, "easy": 1, "question_types": []}]},
    )

    assert response.status_code == 422
    assert "format" in response.json()["error"]["message"]


def test_config_publishes_the_judge_fan_out(client) -> None:
    """The console prices judge calls from this rather than hard-coding four."""
    response = client.get("/api/config")

    assert response.json()["judge_calls_per_question"] == 4
