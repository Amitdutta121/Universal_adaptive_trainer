"""Coverage of the taxonomy by approved questions, and frozen question sets.

Guards ADR-036. The rules most easily lost are that the grid is walked from the
*taxonomy* (so a subtopic with no question still appears) and that a frozen set
is never edited.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace

import book_documents as docs
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llm_fakes import MalformedThenGoodClient, MetricJudgeClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.coverage import (
    MIN_QUESTIONS_PER_CELL,
    CoverageState,
    build_coverage_report,
    create_question_set,
    get_prod_question_set,
    state_for,
    sync_prod_question_set,
)
from app.domain.enums import CurriculumStatus, Difficulty, QuestionStatus
from app.errors import DomainRuleError, NotFoundError
from app.generation.schemas import MultipleChoiceDraft
from app.ingestion import BookImportService
from app.persistence.models import (
    CurriculumVersionRow,
    QuestionRow,
    QuestionSubtopicRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import BookStructureRepository, QuestionSetRepository
from app.retrieval import SectionEmbeddingStore
from app.web.routes.api.coverage import get_generation_client
from app.web.routes.api.retrieval import get_query_embedder


def _taxonomy(session: Session, *, subtopics: int = 1) -> tuple[CurriculumVersionRow, list[int]]:
    """One approved curriculum with a single topic and ``subtopics`` subtopics."""
    version = CurriculumVersionRow(
        label="Intro Python v1",
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    topic = TopicRow(curriculum_version_id=version.id, name="Loops", position=0)
    session.add(topic)
    session.flush()
    ids = []
    for index in range(subtopics):
        subtopic = SubtopicRow(topic_id=topic.id, name=f"Subtopic {index}", position=index)
        session.add(subtopic)
        session.flush()
        ids.append(subtopic.id)
    session.commit()
    return version, ids


def _question(
    session: Session,
    *,
    version: CurriculumVersionRow,
    subtopic_id: int,
    difficulty: Difficulty = Difficulty.EASY,
    status: QuestionStatus = QuestionStatus.APPROVED,
) -> QuestionRow:
    row = QuestionRow(
        prompt="Write a loop.",
        curriculum_version_id=version.id,
        difficulty=difficulty,
        status=status,
        generator_name="base-gen",
        generator_version="1",
    )
    session.add(row)
    session.flush()
    session.add(QuestionSubtopicRow(question_id=row.id, subtopic_id=subtopic_id))
    session.commit()
    return row


# ------------------------------------------------------------------ cell states


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, CoverageState.EMPTY),
        (1, CoverageState.THIN),
        (MIN_QUESTIONS_PER_CELL - 1, CoverageState.THIN),
        (MIN_QUESTIONS_PER_CELL, CoverageState.READY),
        (MIN_QUESTIONS_PER_CELL + 5, CoverageState.READY),
    ],
)
def test_a_cell_state_follows_its_count(count: int, expected: CoverageState) -> None:
    assert state_for(count) is expected


def test_one_question_is_thin_not_ready() -> None:
    """A served question drops to the lowest priority, so one repeats immediately."""
    assert MIN_QUESTIONS_PER_CELL > 1
    assert state_for(1) is CoverageState.THIN


# ------------------------------------------------------------------------- grid


def test_a_subtopic_with_no_questions_still_appears(session: Session) -> None:
    """The row the professor most needs must not fall out of a join."""
    _taxonomy(session, subtopics=2)

    report = build_coverage_report(session)

    assert len(report.subtopics) == 2
    assert report.total_cells == 6
    assert report.empty_cells == 6
    assert report.is_servable is False
    assert report.question_count == 0


def test_the_grid_counts_approved_questions_per_cell(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    for _ in range(MIN_QUESTIONS_PER_CELL):
        _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.EASY)
    _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.MEDIUM)

    report = build_coverage_report(session)
    cells = {cell.difficulty: cell for cell in report.subtopics[0].cells}

    assert cells[Difficulty.EASY].count == MIN_QUESTIONS_PER_CELL
    assert cells[Difficulty.EASY].state is CoverageState.READY
    assert cells[Difficulty.MEDIUM].state is CoverageState.THIN
    assert cells[Difficulty.HARD].state is CoverageState.EMPTY
    assert report.empty_cells == 1
    assert report.thin_cells == 1


def test_only_approved_questions_count(session: Session) -> None:
    """A question that only passed validation carries no professor verdict."""
    version, (subtopic_id,) = _taxonomy(session)
    for status in (QuestionStatus.VALIDATION_PASSED, QuestionStatus.REJECTED):
        _question(session, version=version, subtopic_id=subtopic_id, status=status)

    report = build_coverage_report(session)

    assert report.empty_cells == 3
    assert report.question_count == 0


def test_one_question_can_fill_a_cell_in_several_rows(session: Session) -> None:
    """A question may claim up to three subtopics; the engine finds it under each."""
    version, subtopic_ids = _taxonomy(session, subtopics=3)
    question = _question(session, version=version, subtopic_id=subtopic_ids[0])
    for subtopic_id in subtopic_ids[1:]:
        session.add(QuestionSubtopicRow(question_id=question.id, subtopic_id=subtopic_id))
    session.commit()

    report = build_coverage_report(session)

    assert [row.cells[0].count for row in report.subtopics] == [1, 1, 1]
    # One distinct question, three filled cells. The two must not be conflated.
    assert report.question_count == 1


def test_a_servable_grid_can_still_be_thin(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    for difficulty in Difficulty:
        _question(session, version=version, subtopic_id=subtopic_id, difficulty=difficulty)

    report = build_coverage_report(session)

    assert report.empty_cells == 0
    assert report.is_servable is True
    assert report.is_ready is False, "one question per cell repeats immediately"


def test_a_full_grid_is_ready(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    for difficulty in Difficulty:
        for _ in range(MIN_QUESTIONS_PER_CELL):
            _question(session, version=version, subtopic_id=subtopic_id, difficulty=difficulty)

    report = build_coverage_report(session)

    assert report.is_ready is True
    assert report.gaps == []


def test_gaps_name_the_subtopic_and_difficulty(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.EASY)

    report = build_coverage_report(session)

    assert [(row.subtopic_name, cell.difficulty) for row, cell in report.gaps] == [
        ("Subtopic 0", Difficulty.MEDIUM),
        ("Subtopic 0", Difficulty.HARD),
    ]


def test_no_approved_curriculum_is_reported_as_such_not_as_an_empty_grid(
    session: Session,
) -> None:
    """An empty grid would read as "no subtopic needs questions", the opposite."""
    session.add(CurriculumVersionRow(label="draft", status=CurriculumStatus.PROPOSED))
    session.commit()

    report = build_coverage_report(session)

    assert report.curriculum_version_id is None
    assert report.subtopics == []
    assert report.is_servable is False


# ----------------------------------------------------------------- frozen sets


def test_freezing_a_set_snapshots_the_approved_questions(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    approved = _question(session, version=version, subtopic_id=subtopic_id)
    _question(
        session,
        version=version,
        subtopic_id=subtopic_id,
        status=QuestionStatus.VALIDATION_PASSED,
    )

    row = create_question_set(session, label="Autumn 2026")

    assert row.question_count == 1
    assert [member.question_id for member in row.members] == [approved.id]
    assert row.curriculum_version_id == version.id


def test_a_set_does_not_change_when_the_bank_grows(session: Session) -> None:
    """This is the whole point of freezing: two students must see one bank."""
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id)
    frozen = create_question_set(session, label="Autumn 2026")
    _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.HARD)

    reread = QuestionSetRepository(session).get(frozen.id)

    assert reread.question_count == 1
    assert len(reread.members) == 1
    # The live bank has moved on; the set has not.
    assert len(QuestionSetRepository(session).approved_question_ids()) == 2


def test_syncing_prod_creates_a_snapshot_and_points_the_alias(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    approved = _question(session, version=version, subtopic_id=subtopic_id)

    synced = sync_prod_question_set(session)
    prod = get_prod_question_set(session)

    assert synced.id == prod.id
    assert [member.question_id for member in prod.members] == [approved.id]


def test_syncing_prod_again_moves_the_alias_not_the_old_snapshot(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    first = _question(session, version=version, subtopic_id=subtopic_id)
    original = sync_prod_question_set(session)
    second = _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.HARD)

    moved = sync_prod_question_set(session)
    original_again = QuestionSetRepository(session).get(original.id)

    assert moved.id != original.id
    assert [member.question_id for member in original_again.members] == [first.id]
    assert sorted(member.question_id for member in moved.members) == sorted([first.id, second.id])


def test_the_repository_offers_no_way_to_edit_a_set() -> None:
    """A snapshot that can be edited answers nothing about what was served."""
    forbidden = {"update", "add_member", "remove_member", "set_members", "delete"}
    assert not forbidden & set(dir(QuestionSetRepository))


def test_freezing_refuses_an_empty_set(session: Session) -> None:
    _taxonomy(session)

    with pytest.raises(DomainRuleError):
        create_question_set(session, label="Nothing yet")


def test_freezing_refuses_without_an_approved_curriculum(session: Session) -> None:
    with pytest.raises(DomainRuleError):
        create_question_set(session, label="No taxonomy")


def test_freezing_refuses_a_blank_label(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id)

    with pytest.raises(DomainRuleError):
        create_question_set(session, label="   ")


def test_coverage_of_a_frozen_set_ignores_questions_added_later(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.EASY)
    frozen = create_question_set(session, label="Autumn 2026")
    _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.HARD)

    live = build_coverage_report(session)
    snapshot = build_coverage_report(session, set_version_id=frozen.id)

    assert live.question_count == 2
    assert snapshot.question_count == 1
    assert snapshot.empty_cells == 2
    assert live.empty_cells == 1


def test_an_unknown_set_is_not_found(session: Session) -> None:
    with pytest.raises(NotFoundError):
        build_coverage_report(session, set_version_id=404)


# -------------------------------------------------------------------- endpoint


def test_the_coverage_endpoint_reports_the_grid(client: TestClient, session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.EASY)

    payload = client.get("/api/coverage").json()

    assert payload["curriculum_label"] == "Intro Python v1"
    assert payload["total_cells"] == 3
    assert payload["empty_cells"] == 2
    assert payload["is_servable"] is False
    assert payload["minimum_per_cell"] == MIN_QUESTIONS_PER_CELL
    assert payload["subtopics"][0]["cells"][0]["state"] == "thin"


def test_the_endpoint_creates_and_reads_back_a_set(client: TestClient, session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    approved = _question(session, version=version, subtopic_id=subtopic_id)

    created = client.post("/api/question-sets", json={"label": "Autumn 2026"})
    assert created.status_code == 201
    set_id = created.json()["id"]

    fetched = client.get(f"/api/question-sets/{set_id}").json()
    listed = client.get("/api/question-sets").json()

    assert fetched["question_ids"] == [approved.id]
    assert fetched["question_count"] == fetched["member_count"] == 1
    assert fetched["is_prod"] is False
    assert listed["total"] == 1


def test_the_api_can_sync_and_read_the_current_prod_set(
    client: TestClient, session: Session
) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    approved = _question(session, version=version, subtopic_id=subtopic_id)

    synced = client.post("/api/question-sets/prod/sync")
    assert synced.status_code == 201
    assert synced.json()["is_prod"] is True

    fetched = client.get("/api/question-sets/prod")

    assert fetched.status_code == 200
    assert fetched.json()["question_ids"] == [approved.id]
    assert fetched.json()["is_prod"] is True


def test_question_set_detail_stays_public_for_the_join_lobby(
    settings: Settings, session: Session
) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    approved = _question(session, version=version, subtopic_id=subtopic_id)
    frozen = create_question_set(session, label="Autumn 2026")

    from app.main import create_app

    with TestClient(create_app(settings)) as public_client:
        fetched = public_client.get(f"/api/question-sets/{frozen.id}")

    assert fetched.status_code == 200
    assert fetched.json()["question_ids"] == [approved.id]


def test_the_current_prod_set_is_public_for_the_join_lobby(
    settings: Settings, session: Session
) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    approved = _question(session, version=version, subtopic_id=subtopic_id)
    sync_prod_question_set(session)

    from app.main import create_app

    with TestClient(create_app(settings)) as public_client:
        fetched = public_client.get("/api/question-sets/prod")

    assert fetched.status_code == 200
    assert fetched.json()["question_ids"] == [approved.id]
    assert fetched.json()["is_prod"] is True


def test_creating_an_empty_set_is_refused_by_the_api(client: TestClient, session: Session) -> None:
    _taxonomy(session)

    response = client.post("/api/question-sets", json={"label": "Nothing"})

    assert response.status_code == 422
    assert "nothing to freeze" in response.text.lower()


def test_the_openapi_documents_coverage_as_read_only(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert set(schema["paths"]["/api/coverage"]) == {"get"}
    assert set(schema["paths"]["/api/question-sets"]) == {"get", "post"}
    assert set(schema["paths"]["/api/question-sets/prod"]) == {"get"}
    assert set(schema["paths"]["/api/question-sets/prod/sync"]) == {"post"}
    # No PUT, PATCH or DELETE: a frozen set is never edited (ADR-036).
    assert set(schema["paths"]["/api/question-sets/{set_version_id}"]) == {"get"}


# ------------------------------------------------------------ topic grouping


def test_the_report_groups_rows_by_topic(session: Session) -> None:
    """The unit a professor acts on. A chunk teaches one topic, so a gap in
    another topic is not work they can do in the same breath."""
    version, subtopic_ids = _taxonomy(session, subtopics=2)
    _question(session, version=version, subtopic_id=subtopic_ids[0])

    report = build_coverage_report(session)

    assert [topic.topic_name for topic in report.topics] == ["Loops"]
    topic = report.topics[0]
    assert [row.subtopic_name for row in topic.subtopics] == ["Subtopic 0", "Subtopic 1"]
    assert topic.total_cells == 6
    assert topic.empty_cells == 5
    assert topic.thin_cells == 1
    assert topic.ready_cells == 0
    assert topic.is_complete is False


def test_the_flat_row_list_is_derived_from_the_grouping(session: Session) -> None:
    """One source of truth: two lists of the same rows would eventually
    disagree, and the professor would be reading whichever one did."""
    _, subtopic_ids = _taxonomy(session, subtopics=3)

    report = build_coverage_report(session)

    assert report.subtopics == [row for topic in report.topics for row in topic.subtopics]
    assert [row.subtopic_id for row in report.subtopics] == subtopic_ids


def test_a_cell_reports_what_it_still_owes(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.EASY)

    report = build_coverage_report(session)
    cells = {cell.difficulty: cell for cell in report.subtopics[0].cells}

    assert cells[Difficulty.EASY].needed == MIN_QUESTIONS_PER_CELL - 1
    assert cells[Difficulty.HARD].needed == MIN_QUESTIONS_PER_CELL
    assert report.gap_count == 3
    assert report.questions_needed == MIN_QUESTIONS_PER_CELL * 3 - 1


def test_a_ready_cell_owes_nothing(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    for difficulty in Difficulty:
        for _ in range(MIN_QUESTIONS_PER_CELL + 2):
            _question(session, version=version, subtopic_id=subtopic_id, difficulty=difficulty)

    report = build_coverage_report(session)

    assert report.gap_count == 0
    assert report.questions_needed == 0
    assert report.complete_topics == report.topics
    assert report.incomplete_topics == []


def test_a_topic_counts_distinct_questions_not_filled_cells(session: Session) -> None:
    """A question claiming three subtopics fills three cells but is one question."""
    version, subtopic_ids = _taxonomy(session, subtopics=3)
    question = _question(session, version=version, subtopic_id=subtopic_ids[0])
    question.topic_id = session.get(SubtopicRow, subtopic_ids[0]).topic_id
    for subtopic_id in subtopic_ids[1:]:
        session.add(QuestionSubtopicRow(question_id=question.id, subtopic_id=subtopic_id))
    session.commit()

    report = build_coverage_report(session)

    assert sum(row.cells[0].count for row in report.subtopics) == 3
    assert report.topics[0].approved_questions == 1


def test_a_frozen_set_scopes_the_per_topic_question_count(session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    topic_id = session.get(SubtopicRow, subtopic_id).topic_id
    first = _question(session, version=version, subtopic_id=subtopic_id)
    first.topic_id = topic_id
    session.commit()
    frozen = create_question_set(session, label="Autumn 2026")
    later = _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.HARD)
    later.topic_id = topic_id
    session.commit()

    live = build_coverage_report(session)
    snapshot = build_coverage_report(session, set_version_id=frozen.id)

    assert live.topics[0].approved_questions == 2
    assert snapshot.topics[0].approved_questions == 1


def test_the_endpoint_publishes_the_topic_grouping(client: TestClient, session: Session) -> None:
    version, (subtopic_id,) = _taxonomy(session)
    _question(session, version=version, subtopic_id=subtopic_id, difficulty=Difficulty.EASY)

    payload = client.get("/api/coverage").json()

    assert payload["gap_count"] == 3
    assert payload["ready_cells"] == 0
    assert [topic["topic_name"] for topic in payload["topics"]] == ["Loops"]
    assert payload["topics"][0]["subtopics"][0]["cells"][0]["needed"] == MIN_QUESTIONS_PER_CELL - 1


# -------------------------------------------- generate for gaps (m2)


class KeywordEmbedder:
    """Deterministic bag-of-words embedder over a fixed vocabulary.

    Cosine ordering is then a function of shared keywords, so a "while loop"
    query ranks the while-loop section first and a query with none of the
    vocabulary embeds to a zero vector -- the retriever's "nothing" case.
    """

    model = "keyword-test-v1"
    VOCAB = ("loop", "while", "range", "variable", "string", "slice")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(t.lower().count(word)) for word in self.VOCAB] for t in texts]


def _gen_book(session: Session, settings: Settings):
    sections = [
        "A while loop repeats while a condition holds. Use a while loop to loop again.",
        "A string can be sliced. Take a slice of a string. string slice string.",
        "A variable is a name that refers to a value. variable variable.",
    ]
    doc = {
        "schema_version": "1",
        "title": "Gen Book",
        "chapters": [{"sections": [{"text": text} for text in sections]}],
    }
    book = BookImportService(session, settings).import_upload(
        filename="gen_book.json", data=docs.to_bytes(doc)
    )
    session.commit()
    return book


def _gen_taxonomy(session: Session, book_id: int):
    version = CurriculumVersionRow(
        label="Gen v1",
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
        source_book_ids=[book_id],
    )
    session.add(version)
    session.flush()
    loops = TopicRow(curriculum_version_id=version.id, name="Loops", position=0)
    strings = TopicRow(curriculum_version_id=version.id, name="Strings", position=1)
    advanced = TopicRow(curriculum_version_id=version.id, name="Advanced", position=2)
    session.add_all([loops, strings, advanced])
    session.flush()
    while_loops = SubtopicRow(
        topic_id=loops.id,
        name="While loops",
        description="Using a while loop to repeat a block.",
        position=0,
    )
    slicing = SubtopicRow(
        topic_id=strings.id,
        name="Slicing",
        description="Taking a slice of a string.",
        position=0,
    )
    recursion = SubtopicRow(
        topic_id=advanced.id,
        name="Recursion",
        description="A function that calls itself.",
        position=0,
    )
    session.add_all([while_loops, slicing, recursion])
    session.commit()
    return SimpleNamespace(
        version=version, while_loops=while_loops, slicing=slicing, recursion=recursion
    )


def _mcq(topic_id: int, subtopic_id: int) -> MultipleChoiceDraft:
    return MultipleChoiceDraft(
        topic_id=topic_id,
        subtopic_ids=[subtopic_id],
        prompt="Which loop repeats while a condition holds?",
        options=["while loop", "for loop", "do loop", "no loop"],
        correct_option_index=0,
        explanation="A while loop runs while its condition is true.",
    )


@pytest.fixture
def gen_env(session: Session, settings: Settings) -> SimpleNamespace:
    book = _gen_book(session, settings)
    env = _gen_taxonomy(session, book.id)
    SectionEmbeddingStore(session, KeywordEmbedder()).backfill()
    session.commit()
    env.book = book
    env.sections = BookStructureRepository(session).sections_in_book(book.id)
    return env


def _run(app: FastAPI, gen_client: object, targets: list[dict]) -> object:
    app.dependency_overrides[get_query_embedder] = KeywordEmbedder
    app.dependency_overrides[get_generation_client] = lambda: gen_client
    with TestClient(app) as http:
        return http.post("/api/coverage/generation-runs", json={"targets": targets})


def test_a_run_generates_a_grounded_question_into_the_review_queue(
    configured_app: FastAPI, session: Session, gen_env: SimpleNamespace
) -> None:
    client = MetricJudgeClient(draft=_mcq(gen_env.while_loops.topic_id, gen_env.while_loops.id))

    response = _run(
        configured_app,
        client,
        [{"subtopic_id": gen_env.while_loops.id, "difficulty": "medium"}],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"]
    assert body["skipped"] == [] and body["failed"] == []
    (produced,) = body["generated"]
    assert produced["requested_subtopic_id"] == gen_env.while_loops.id
    assert produced["requested_difficulty"] == "medium"
    assert produced["claimed_topic_id"] == gen_env.while_loops.topic_id
    assert produced["aim_matched"] is True
    assert produced["section_id"] == gen_env.sections[0].id
    assert produced["status"] == "validation_passed"

    with TestClient(configured_app) as http:
        listed = http.get("/api/questions", params={"status": "validation_passed"}).json()
    assert produced["question_id"] in [q["id"] for q in listed["questions"]]


def test_a_run_surfaces_an_aim_mismatch_without_filtering_it(
    configured_app: FastAPI, session: Session, gen_env: SimpleNamespace
) -> None:
    """The generator classified the question under a different topic than the
    gap it was retrieved for (ADR-031). It is reported, not dropped."""
    client = MetricJudgeClient(draft=_mcq(gen_env.slicing.topic_id, gen_env.slicing.id))

    response = _run(
        configured_app,
        client,
        [{"subtopic_id": gen_env.while_loops.id, "difficulty": "easy"}],
    )

    assert response.status_code == 200, response.text
    (produced,) = response.json()["generated"]
    assert produced["requested_subtopic_id"] == gen_env.while_loops.id
    assert produced["claimed_topic_id"] == gen_env.slicing.topic_id
    assert produced["aim_matched"] is False


def test_a_target_with_no_confident_section_is_skipped_and_the_run_continues(
    configured_app: FastAPI, session: Session, gen_env: SimpleNamespace
) -> None:
    client = MetricJudgeClient(draft=_mcq(gen_env.while_loops.topic_id, gen_env.while_loops.id))

    response = _run(
        configured_app,
        client,
        [
            {"subtopic_id": gen_env.recursion.id, "difficulty": "easy"},
            {"subtopic_id": gen_env.while_loops.id, "difficulty": "medium"},
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skipped"] == [
        {
            "subtopic_id": gen_env.recursion.id,
            "difficulty": "easy",
            "reason": "no confident section",
        }
    ]
    assert [q["requested_subtopic_id"] for q in body["generated"]] == [gen_env.while_loops.id]


def test_a_below_floor_section_is_skipped(
    configured_app: FastAPI,
    session: Session,
    gen_env: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.web.routes.api.coverage.MIN_SECTION_SCORE", 0.999)
    client = MetricJudgeClient(draft=_mcq(gen_env.while_loops.topic_id, gen_env.while_loops.id))

    response = _run(
        configured_app,
        client,
        [{"subtopic_id": gen_env.while_loops.id, "difficulty": "hard"}],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generated"] == []
    assert body["skipped"][0]["reason"] == "no confident section"


def test_an_unknown_subtopic_is_a_404_before_anything_is_generated(
    configured_app: FastAPI, session: Session, gen_env: SimpleNamespace
) -> None:
    client = MetricJudgeClient(draft=_mcq(gen_env.while_loops.topic_id, gen_env.while_loops.id))

    response = _run(configured_app, client, [{"subtopic_id": 999999, "difficulty": "hard"}])

    assert response.status_code == 404
    with TestClient(configured_app) as http:
        assert http.get("/api/questions").json()["total"] == 0


def test_a_provider_failure_on_one_target_keeps_the_others(
    configured_app: FastAPI, session: Session, gen_env: SimpleNamespace
) -> None:
    # Malformed for the first target's whole retry budget, then answers normally.
    client = MalformedThenGoodClient(
        malformed_replies=3,
        draft=_mcq(gen_env.while_loops.topic_id, gen_env.while_loops.id),
    )

    response = _run(
        configured_app,
        client,
        [
            {"subtopic_id": gen_env.slicing.id, "difficulty": "easy"},
            {"subtopic_id": gen_env.while_loops.id, "difficulty": "medium"},
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    (failed,) = body["failed"]
    assert failed["subtopic_id"] == gen_env.slicing.id
    assert failed["section_id"] == gen_env.sections[1].id
    assert failed["error"]
    assert [q["requested_subtopic_id"] for q in body["generated"]] == [gen_env.while_loops.id]

    with TestClient(configured_app) as http:
        listed = http.get("/api/questions", params={"status": "validation_passed"}).json()
    assert [q["id"] for q in listed["questions"]] == [body["generated"][0]["question_id"]]


def test_asking_to_fill_no_gaps_at_all_is_rejected(configured_app: FastAPI) -> None:
    response = _run(configured_app, MetricJudgeClient(), [])

    assert response.status_code == 422
