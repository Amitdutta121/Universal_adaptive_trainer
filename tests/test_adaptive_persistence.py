"""Student progress tables and their repositories (ADR-041).

Guards the rules most easily lost: reads never seed state rows, the roulette is
weighted only over subtopics a set can answer, a since-rejected question stops
being servable, and an unanswered attempt stays open.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus, Difficulty, QuestionStatus
from app.domain.mastery import DEFAULT_BKT_PARAMETERS, INITIAL_SUBTOPIC_WEAKNESS
from app.errors import NotFoundError
from app.persistence.models import (
    CurriculumVersionRow,
    QuestionRow,
    QuestionSubtopicRow,
    StudentAttemptRow,
    StudentSubtopicWeaknessRow,
    StudentTopicMasteryRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import (
    QuestionSetRepository,
    StudentAttemptRepository,
    StudentRepository,
    StudentStateRepository,
    TrainingSessionRepository,
)


def _taxonomy(
    session: Session, *, subtopics: int = 2
) -> tuple[CurriculumVersionRow, int, list[int]]:
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
    subtopic_ids = []
    for index in range(subtopics):
        subtopic = SubtopicRow(topic_id=topic.id, name=f"Subtopic {index}", position=index)
        session.add(subtopic)
        session.flush()
        subtopic_ids.append(subtopic.id)
    session.commit()
    return version, topic.id, subtopic_ids


def _question(
    session: Session,
    *,
    version: CurriculumVersionRow,
    topic_id: int,
    subtopic_id: int,
    difficulty: Difficulty = Difficulty.EASY,
    status: QuestionStatus = QuestionStatus.APPROVED,
    priority: int = 100,
    times_used: int = 0,
) -> QuestionRow:
    row = QuestionRow(
        prompt="Write a loop.",
        curriculum_version_id=version.id,
        topic_id=topic_id,
        difficulty=difficulty,
        status=status,
        priority=priority,
        times_used=times_used,
        generator_name="base-gen",
        generator_version="1",
    )
    session.add(row)
    session.flush()
    session.add(QuestionSubtopicRow(question_id=row.id, subtopic_id=subtopic_id))
    session.commit()
    return row


class TestStudentRepository:
    """A student is a named row, because there is no authentication."""

    def test_a_student_can_be_created_and_read_back(self, session: Session) -> None:
        repo = StudentRepository(session)
        created = repo.add("Ada")
        session.commit()
        assert repo.get(created.id).display_name == "Ada"
        assert repo.count() == 1

    def test_students_are_listed_by_name(self, session: Session) -> None:
        repo = StudentRepository(session)
        repo.add("Zoe")
        repo.add("Ada")
        session.commit()
        assert [row.display_name for row in repo.list_all()] == ["Ada", "Zoe"]

    def test_a_missing_student_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            StudentRepository(session).get(404)

    def test_an_unknown_name_reads_as_none(self, session: Session) -> None:
        assert StudentRepository(session).get_by_name("Nobody") is None

    def test_two_students_cannot_share_a_name(self, session: Session) -> None:
        """The picker is by name, so a duplicate would attach mastery to the wrong learner."""
        repo = StudentRepository(session)
        repo.add("Ada")
        session.commit()
        with pytest.raises(IntegrityError):
            repo.add("Ada")
        session.rollback()


class TestStudentState:
    """Reads never create a row; writes do."""

    def test_an_unscored_topic_reads_as_the_bkt_prior(self, session: Session) -> None:
        state = StudentStateRepository(session)
        assert state.mastery_for(1, 1) == DEFAULT_BKT_PARAMETERS.p_init

    def test_an_unscored_subtopic_reads_as_maximum_weakness(self, session: Session) -> None:
        state = StudentStateRepository(session)
        assert state.weaknesses_for(1, [7]) == {7: INITIAL_SUBTOPIC_WEAKNESS}

    def test_reading_state_seeds_nothing(self, session: Session) -> None:
        """Rendering a progress page must not write a row per subtopic (ADR-041)."""
        state = StudentStateRepository(session)
        state.mastery_for(1, 1)
        state.weaknesses_for(1, [1, 2, 3])
        session.commit()
        assert session.query(StudentTopicMasteryRow).count() == 0
        assert session.query(StudentSubtopicWeaknessRow).count() == 0

    def test_every_requested_subtopic_appears_in_the_result(self, session: Session) -> None:
        state = StudentStateRepository(session)
        state.record_weakness(1, 2, 0.4)
        session.commit()
        assert state.weaknesses_for(1, [1, 2, 3]) == {
            1: INITIAL_SUBTOPIC_WEAKNESS,
            2: 0.4,
            3: INITIAL_SUBTOPIC_WEAKNESS,
        }

    def test_asking_for_no_subtopics_returns_nothing(self, session: Session) -> None:
        assert StudentStateRepository(session).weaknesses_for(1, []) == {}

    def test_recording_mastery_creates_then_updates_one_row(self, session: Session) -> None:
        state = StudentStateRepository(session)
        state.record_mastery(1, 5, 0.6)
        state.record_mastery(1, 5, 0.8)
        session.commit()
        rows = state.list_mastery(1)
        assert len(rows) == 1
        assert rows[0].p_known == 0.8
        assert rows[0].observations == 2

    def test_recording_weakness_creates_then_updates_one_row(self, session: Session) -> None:
        state = StudentStateRepository(session)
        state.record_weakness(1, 5, 0.7)
        state.record_weakness(1, 5, 0.49)
        session.commit()
        rows = state.list_weakness(1)
        assert len(rows) == 1
        assert rows[0].weakness == 0.49
        assert rows[0].observations == 2

    def test_an_update_stamps_a_change_time(self, session: Session) -> None:
        state = StudentStateRepository(session)
        first = state.record_mastery(1, 5, 0.6)
        assert first.updated_at is None
        second = state.record_mastery(1, 5, 0.7)
        assert second.updated_at is not None

    def test_two_students_keep_separate_state(self, session: Session) -> None:
        """The whole point of per-student records: two learners diverge."""
        state = StudentStateRepository(session)
        state.record_mastery(1, 5, 0.9)
        state.record_mastery(2, 5, 0.1)
        session.commit()
        assert state.mastery_for(1, 5) == 0.9
        assert state.mastery_for(2, 5) == 0.1


class TestTrainingSessions:
    """A run is pinned to one frozen set (ADR-036)."""

    def test_a_session_records_its_set_and_seed(self, session: Session) -> None:
        student = StudentRepository(session).add("Ada")
        sets = QuestionSetRepository(session)
        frozen = sets.create(label="Week 1", question_ids=[], curriculum_version_id=None)
        session.commit()

        runs = TrainingSessionRepository(session)
        created = runs.create(student_id=student.id, set_version_id=frozen.id, rng_seed=42)
        session.commit()

        stored = runs.get(created.id)
        assert stored.set_version_id == frozen.id
        assert stored.rng_seed == 42
        assert stored.ended_at is None

    def test_a_missing_session_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            TrainingSessionRepository(session).get(404)

    def test_ending_a_session_stamps_it(self, session: Session) -> None:
        student = StudentRepository(session).add("Ada")
        runs = TrainingSessionRepository(session)
        created = runs.create(student_id=student.id, set_version_id=1, rng_seed=1)
        session.commit()
        assert runs.end(created).ended_at is not None

    def test_sessions_are_listed_newest_first(self, session: Session) -> None:
        student = StudentRepository(session).add("Ada")
        runs = TrainingSessionRepository(session)
        first = runs.create(student_id=student.id, set_version_id=1, rng_seed=1)
        second = runs.create(student_id=student.id, set_version_id=1, rng_seed=2)
        session.commit()
        listed = [row.id for row in runs.list_for_student(student.id)]
        assert listed == [second.id, first.id]


class TestAttempts:
    """An attempt is written when the question is served, not when it is answered."""

    def _served(
        self,
        session: Session,
        *,
        student_id: int,
        session_id: int,
        question_id: int,
        ordinal: int = 1,
    ) -> StudentAttemptRow:
        return StudentAttemptRepository(session).add(
            StudentAttemptRow(
                session_id=session_id,
                student_id=student_id,
                question_id=question_id,
                ordinal=ordinal,
                requested_difficulty=Difficulty.EASY,
                served_difficulty=Difficulty.EASY,
            )
        )

    def test_a_served_question_is_open_until_it_is_scored(self, session: Session) -> None:
        attempts = StudentAttemptRepository(session)
        served = self._served(session, student_id=1, session_id=1, question_id=1)
        session.commit()
        assert attempts.open_attempt(1) is not None

        served.score = 80.0
        served.answered_at = datetime.now(UTC)
        session.commit()
        assert attempts.open_attempt(1) is None

    def test_ordinals_count_from_one(self, session: Session) -> None:
        attempts = StudentAttemptRepository(session)
        assert attempts.next_ordinal(1) == 1
        self._served(session, student_id=1, session_id=1, question_id=1, ordinal=1)
        session.commit()
        assert attempts.next_ordinal(1) == 2

    def test_one_ordinal_cannot_be_used_twice_in_a_session(self, session: Session) -> None:
        self._served(session, student_id=1, session_id=1, question_id=1, ordinal=1)
        session.commit()
        with pytest.raises(IntegrityError):
            self._served(session, student_id=1, session_id=1, question_id=2, ordinal=1)
        session.rollback()

    def test_only_scored_questions_count_as_answered(self, session: Session) -> None:
        attempts = StudentAttemptRepository(session)
        scored = self._served(session, student_id=1, session_id=1, question_id=11, ordinal=1)
        scored.score = 100.0
        self._served(session, student_id=1, session_id=1, question_id=22, ordinal=2)
        session.commit()
        assert attempts.answered_question_ids(1) == {11}

    def test_answered_questions_span_every_session(self, session: Session) -> None:
        """Meeting the same question in a new session is the same repeat."""
        attempts = StudentAttemptRepository(session)
        first = self._served(session, student_id=1, session_id=1, question_id=11, ordinal=1)
        first.score = 50.0
        second = self._served(session, student_id=1, session_id=2, question_id=22, ordinal=1)
        second.score = 50.0
        session.commit()
        assert attempts.answered_question_ids(1) == {11, 22}

    def test_one_students_history_is_not_anothers(self, session: Session) -> None:
        attempts = StudentAttemptRepository(session)
        mine = self._served(session, student_id=1, session_id=1, question_id=11, ordinal=1)
        mine.score = 100.0
        theirs = self._served(session, student_id=2, session_id=2, question_id=22, ordinal=1)
        theirs.score = 100.0
        session.commit()
        assert attempts.answered_question_ids(1) == {11}
        assert attempts.count_answered(2) == 1

    def test_a_missing_attempt_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            StudentAttemptRepository(session).get(404)


class TestServableQuestions:
    """What a frozen set can actually answer a request for."""

    def test_only_subtopics_with_a_question_are_weighted(self, session: Session) -> None:
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=3)
        covered = _question(
            session, version=version, topic_id=topic_id, subtopic_id=subtopic_ids[0]
        )
        sets = QuestionSetRepository(session)
        frozen = sets.create(
            label="Week 1", question_ids=[covered.id], curriculum_version_id=version.id
        )
        session.commit()

        assert sets.servable_subtopic_ids(frozen.id) == {subtopic_ids[0]}

    def test_a_cell_yields_its_questions_with_selection_fields(self, session: Session) -> None:
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=1)
        first = _question(
            session,
            version=version,
            topic_id=topic_id,
            subtopic_id=subtopic_ids[0],
            priority=100,
            times_used=0,
        )
        second = _question(
            session,
            version=version,
            topic_id=topic_id,
            subtopic_id=subtopic_ids[0],
            priority=0,
            times_used=3,
        )
        sets = QuestionSetRepository(session)
        frozen = sets.create(
            label="Week 1",
            question_ids=[first.id, second.id],
            curriculum_version_id=version.id,
        )
        session.commit()

        found = sets.candidates_for_cell(
            frozen.id, subtopic_id=subtopic_ids[0], difficulty=Difficulty.EASY
        )
        assert found == [(first.id, 100, 0), (second.id, 0, 3)]

    def test_a_different_difficulty_is_a_different_cell(self, session: Session) -> None:
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=1)
        easy = _question(
            session,
            version=version,
            topic_id=topic_id,
            subtopic_id=subtopic_ids[0],
            difficulty=Difficulty.EASY,
        )
        sets = QuestionSetRepository(session)
        frozen = sets.create(
            label="Week 1", question_ids=[easy.id], curriculum_version_id=version.id
        )
        session.commit()

        assert (
            sets.candidates_for_cell(
                frozen.id, subtopic_id=subtopic_ids[0], difficulty=Difficulty.HARD
            )
            == []
        )

    def test_a_question_rejected_after_freezing_stops_being_served(self, session: Session) -> None:
        """A set is immutable, but withdrawn approval must still reach selection."""
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=1)
        question = _question(
            session, version=version, topic_id=topic_id, subtopic_id=subtopic_ids[0]
        )
        sets = QuestionSetRepository(session)
        frozen = sets.create(
            label="Week 1", question_ids=[question.id], curriculum_version_id=version.id
        )
        session.commit()
        assert sets.servable_subtopic_ids(frozen.id) == {subtopic_ids[0]}

        question.status = QuestionStatus.REJECTED
        session.commit()

        assert sets.servable_subtopic_ids(frozen.id) == set()
        assert (
            sets.candidates_for_cell(
                frozen.id, subtopic_id=subtopic_ids[0], difficulty=Difficulty.EASY
            )
            == []
        )

    def test_a_question_outside_the_set_is_never_offered(self, session: Session) -> None:
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=1)
        inside = _question(session, version=version, topic_id=topic_id, subtopic_id=subtopic_ids[0])
        _question(session, version=version, topic_id=topic_id, subtopic_id=subtopic_ids[0])
        sets = QuestionSetRepository(session)
        frozen = sets.create(
            label="Week 1", question_ids=[inside.id], curriculum_version_id=version.id
        )
        session.commit()

        found = sets.candidates_for_cell(
            frozen.id, subtopic_id=subtopic_ids[0], difficulty=Difficulty.EASY
        )
        assert [question_id for question_id, _, _ in found] == [inside.id]
