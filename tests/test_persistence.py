"""Persistence layer: schema bootstrap and repositories."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

from app.domain.enums import (
    ClaimViolation,
    CurriculumStatus,
    Difficulty,
    GeneratorKind,
    QuestionKind,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.domain.questions import GenerationAttempt, QuestionValidationReport
from app.errors import NotFoundError, SchemaOutOfDateError
from app.feedback import submit_review
from app.persistence.database import init_db, verify_schema
from app.persistence.models import (
    BookRow,
    CurriculumVersionRow,
    QuestionRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import (
    BookRepository,
    CurriculumRepository,
    ProfessorReviewRepository,
    QuestionRepository,
)

EXPECTED_TABLES = {
    "books",
    "book_chapters",
    "book_sections",
    "curriculum_versions",
    "topics",
    "subtopics",
    "questions",
    "professor_reviews",
}


def test_init_db_creates_the_expected_tables(engine: Engine) -> None:
    assert EXPECTED_TABLES.issubset(set(inspect(engine).get_table_names()))


def test_init_db_is_idempotent(engine: Engine) -> None:
    init_db(engine)
    init_db(engine)
    assert EXPECTED_TABLES.issubset(set(inspect(engine).get_table_names()))


class TestSchemaDriftGuard:
    """There is no migration tool, so drift must be reported, not discovered later."""

    def test_a_matching_schema_passes(self, engine: Engine) -> None:
        verify_schema(engine)

    def test_a_missing_column_is_reported_with_the_remedy(self, engine: Engine) -> None:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE books DROP COLUMN checksum_sha256"))

        with pytest.raises(SchemaOutOfDateError) as exc_info:
            verify_schema(engine)

        assert "books.checksum_sha256" in (exc_info.value.detail or "")
        assert "delete the database file" in (exc_info.value.detail or "")


def test_book_repository_roundtrip(session: Session) -> None:
    repo = BookRepository(session)
    assert repo.count() == 0

    stored = repo.add(BookRow(title="Think Python", original_filename="think_python.pdf"))
    session.commit()

    assert repo.count() == 1
    assert stored.id is not None
    assert repo.get(stored.id).title == "Think Python"
    assert [b.title for b in repo.list_recent()] == ["Think Python"]


def test_book_repository_raises_for_a_missing_id(session: Session) -> None:
    with pytest.raises(NotFoundError):
        BookRepository(session).get(4242)


def test_curriculum_tree_is_persisted(session: Session) -> None:
    repo = CurriculumRepository(session)
    version = CurriculumVersionRow(label="Intro Python v1")
    version.topics.append(
        TopicRow(
            name="Control flow",
            position=0,
            subtopics=[
                SubtopicRow(name="if / elif / else", position=0),
                SubtopicRow(name="while loops", position=1),
            ],
        )
    )
    repo.add(version)
    session.commit()

    loaded = repo.list_versions()
    assert len(loaded) == 1
    assert loaded[0].label == "Intro Python v1"
    assert [s.name for s in loaded[0].topics[0].subtopics] == ["if / elif / else", "while loops"]


def test_get_approved_returns_none_until_a_version_is_approved(session: Session) -> None:
    repo = CurriculumRepository(session)
    repo.add(CurriculumVersionRow(label="proposal", status=CurriculumStatus.PROPOSED))
    session.commit()
    assert repo.get_approved() is None

    repo.add(CurriculumVersionRow(label="approved", status=CurriculumStatus.APPROVED))
    session.commit()
    approved = repo.get_approved()
    assert approved is not None
    assert approved.label == "approved"


def test_question_generator_provenance_is_stored(session: Session) -> None:
    repo = QuestionRepository(session)
    stored = repo.add(
        QuestionRow(
            prompt="Reverse a string.",
            original_prompt="Reverse a string.",
            generator_kind=GeneratorKind.PERSONALIZED,
            generator_name="pref-tuned",
            generator_version="2",
        )
    )
    session.commit()

    assert stored.id is not None
    loaded = repo.get(stored.id)
    assert loaded.generator_kind == GeneratorKind.PERSONALIZED
    assert loaded.generator_version == "2"
    assert repo.count_by_status() == {"generated": 1}


def test_generation_attempts_round_trip_through_the_column(session: Session) -> None:
    """The attempt history is typed on the way out, not a raw JSON blob (ADR-032)."""
    repo = QuestionRepository(session)
    stored = repo.add(
        QuestionRow(
            prompt="Reverse a string.",
            original_prompt="Reverse a string.",
            generation_attempts=[
                GenerationAttempt(
                    number=1,
                    claimed_topic_id=11,
                    claimed_subtopic_ids=[106],
                    violations=[ClaimViolation.FOREIGN_SUBTOPICS],
                    detail="Subtopic id(s) not under topic 11: [106].",
                    accepted=False,
                    model="fake/model",
                ),
                GenerationAttempt(
                    number=2, claimed_topic_id=11, claimed_subtopic_ids=[112], accepted=True
                ),
            ],
        )
    )
    session.commit()
    session.expunge_all()

    loaded = repo.get(stored.id)
    assert [attempt.number for attempt in loaded.generation_attempts] == [1, 2]
    assert loaded.generation_attempts[0].violations == [ClaimViolation.FOREIGN_SUBTOPICS]
    assert loaded.generation_attempts[0].claimed_subtopic_ids == [106]
    assert loaded.generation_attempts[1].accepted


def test_a_question_without_attempts_reads_as_an_empty_list(session: Session) -> None:
    """Rows written before ADR-032 must not read back as ``None``."""
    repo = QuestionRepository(session)
    stored = repo.add(QuestionRow(prompt="Sum a list.", original_prompt="Sum a list."))
    session.commit()
    session.expunge_all()

    assert repo.get(stored.id).generation_attempts == []


def test_count_reviewable_excludes_questions_that_failed_validation(session: Session) -> None:
    repo = QuestionRepository(session)
    repo.add(
        QuestionRow(
            prompt="Kept.", original_prompt="Kept.", status=QuestionStatus.VALIDATION_PASSED
        )
    )
    repo.add(
        QuestionRow(
            prompt="Refused.",
            original_prompt="Refused.",
            status=QuestionStatus.VALIDATION_FAILED,
        )
    )
    session.commit()

    assert repo.count() == 2
    assert repo.count_reviewable() == 1
    assert [row.prompt for row in repo.list_unreviewed()] == ["Kept."]


def test_list_recent_filters_by_status(session: Session) -> None:
    repo = QuestionRepository(session)
    repo.add(
        QuestionRow(
            prompt="Kept.", original_prompt="Kept.", status=QuestionStatus.VALIDATION_PASSED
        )
    )
    repo.add(
        QuestionRow(
            prompt="Refused.",
            original_prompt="Refused.",
            status=QuestionStatus.VALIDATION_FAILED,
        )
    )
    session.commit()

    assert len(repo.list_recent()) == 2
    assert [
        row.prompt for row in repo.list_recent(statuses=[QuestionStatus.VALIDATION_FAILED])
    ] == ["Refused."]
    # An empty collection means "nothing matches", not "no filter".
    assert repo.list_recent(statuses=[]) == []


def test_count_by_source_section_reports_reuse_per_section(session: Session) -> None:
    repo = QuestionRepository(session)
    for section_id in (7, 7, 9):
        repo.add(
            QuestionRow(
                prompt="Reverse a string.",
                original_prompt="Reverse a string.",
                spec={"source_section_ids": [section_id]},
            )
        )
    session.commit()

    assert repo.count_by_source_section() == {7: 2, 9: 1}


def test_count_by_source_section_falls_back_to_the_stored_sources(session: Session) -> None:
    """A row with no frozen spec still reports against its recorded source."""
    repo = QuestionRepository(session)
    repo.add(
        QuestionRow(
            prompt="Sum a list.",
            original_prompt="Sum a list.",
            content={"sources": [{"section_id": 3, "citation": "Book, Page 1"}]},
        )
    )
    repo.add(QuestionRow(prompt="No provenance.", original_prompt="No provenance."))
    session.commit()

    assert repo.count_by_source_section() == {3: 1}


def test_submit_review_copies_the_generator_identity(session: Session) -> None:
    question = QuestionRepository(session).add(
        QuestionRow(
            prompt="Sum a list.",
            original_prompt="Sum a list.",
            generator_name="base-gen",
            generator_version="1",
        )
    )
    session.commit()
    assert question.id is not None

    review = submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.EDIT,
        comment="Too easy.",
        prompt="Sum every value in a list.",
        reference_solution="",
        tests="",
    )
    session.commit()

    assert review.reviewed_generator_name == "base-gen"
    assert review.reviewed_generator_version == "1"
    assert ProfessorReviewRepository(session).count() == 1


def test_reviews_are_append_only(session: Session) -> None:
    question = QuestionRepository(session).add(
        QuestionRow(prompt="Count vowels.", original_prompt="Count vowels.")
    )
    session.commit()
    assert question.id is not None

    submit_review(
        session,
        question_id=question.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
    )
    submit_review(session, question_id=question.id, decision=ReviewDecision.APPROVE)
    session.commit()

    decisions = {r.decision for r in ProfessorReviewRepository(session).list_recent()}
    assert decisions == {ReviewDecision.REJECT, ReviewDecision.APPROVE}


def test_submit_review_rejects_an_unknown_question(session: Session) -> None:
    with pytest.raises(NotFoundError):
        submit_review(session, question_id=999, decision=ReviewDecision.APPROVE)


def test_question_row_stores_spec_and_content(session: Session) -> None:
    row = QuestionRow(
        curriculum_version_id=None,
        topic_id=None,
        subtopic_ids=[],
        kind=QuestionKind.DISCRETE,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=Difficulty.EASY,
        status=QuestionStatus.GENERATED,
        prompt="Strings are immutable.",
        reference_solution="true",
        tests=None,
        spec={"topic_id": 1},
        content={"explanation": "because..."},
        validation_report=QuestionValidationReport(checks=[]),
        pedagogical_eval={"status": "skipped"},
        generator_kind=GeneratorKind.BASE,
        generator_name="base",
        generator_version="1",
    )
    saved = QuestionRepository(session).add(row)
    session.commit()
    loaded = QuestionRepository(session).get(saved.id)
    assert loaded.question_type == QuestionType.TRUE_FALSE
    assert loaded.spec == {"topic_id": 1}
    assert loaded.content == {"explanation": "because..."}
    assert loaded.validation_report is not None
    assert loaded.validation_report.checks == []
    assert loaded.pedagogical_eval == {"status": "skipped"}
