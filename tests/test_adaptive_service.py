"""The adaptive engine end to end (ADR-041).

Runs the real loop against a temporary database: roulette, difficulty from
mastery, priority-ordered selection, scoring, and the two state updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.adaptive.service import AdaptiveTrainingEngine
from app.adaptive.state import MIN_SUBTOPIC_WEAKNESS
from app.domain.enums import CurriculumStatus, Difficulty, QuestionStatus, QuestionType
from app.domain.mastery import DEFAULT_BKT_PARAMETERS, INITIAL_SUBTOPIC_WEAKNESS
from app.domain.questions import DEFAULT_PRIORITY, LOWEST_PRIORITY
from app.errors import (
    CurriculumCompletedError,
    DomainRuleError,
    NoQuestionAvailableError,
    NotFoundError,
)
from app.persistence.models import (
    CurriculumVersionRow,
    QuestionRow,
    QuestionSubtopicRow,
    StudentAttemptRow,
    SubtopicRow,
    TopicRow,
    TrainingSessionRow,
)
from app.persistence.repositories import (
    QuestionSetRepository,
    StudentAttemptRepository,
    StudentRepository,
    StudentStateRepository,
    TrainingSessionRepository,
)


@dataclass
class Bank:
    """A curriculum, a student and a frozen set, ready to train against."""

    version: CurriculumVersionRow
    topic_id: int
    subtopic_ids: list[int]
    student_id: int
    set_id: int
    run: TrainingSessionRow


def _taxonomy(session: Session, *, subtopics: int) -> tuple[CurriculumVersionRow, int, list[int]]:
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
    return version, topic.id, ids


def _true_false(
    session: Session,
    *,
    version: CurriculumVersionRow,
    topic_id: int,
    subtopic_ids: list[int],
    difficulty: Difficulty = Difficulty.EASY,
    priority: int = DEFAULT_PRIORITY,
    correct: bool = True,
) -> QuestionRow:
    """An approved true/false question, so scoring needs no subprocess."""
    row = QuestionRow(
        prompt="Lists are mutable.",
        curriculum_version_id=version.id,
        topic_id=topic_id,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=difficulty,
        status=QuestionStatus.APPROVED,
        priority=priority,
        content={
            "prompt": "Lists are mutable.",
            "correct_answer": correct,
            "explanation": "They are.",
        },
        generator_name="base-gen",
        generator_version="1",
    )
    session.add(row)
    session.flush()
    for subtopic_id in subtopic_ids:
        session.add(QuestionSubtopicRow(question_id=row.id, subtopic_id=subtopic_id))
    session.commit()
    return row


def _bank(
    session: Session,
    *,
    subtopics: int = 1,
    questions: int = 1,
    difficulty: Difficulty = Difficulty.EASY,
    seed: int = 7,
    name: str = "Ada",
) -> Bank:
    version, topic_id, subtopic_ids = _taxonomy(session, subtopics=subtopics)
    made = [
        _true_false(
            session,
            version=version,
            topic_id=topic_id,
            subtopic_ids=subtopic_ids,
            difficulty=difficulty,
        )
        for _ in range(questions)
    ]
    student = StudentRepository(session).add(name)
    frozen = QuestionSetRepository(session).create(
        label="Week 1",
        question_ids=[row.id for row in made],
        curriculum_version_id=version.id,
    )
    run = TrainingSessionRepository(session).create(
        student_id=student.id, set_version_id=frozen.id, rng_seed=seed
    )
    session.commit()
    return Bank(
        version=version,
        topic_id=topic_id,
        subtopic_ids=subtopic_ids,
        student_id=student.id,
        set_id=frozen.id,
        run=run,
    )


@dataclass
class SequentialBank:
    """A multi-topic curriculum, a student and a frozen set spanning it."""

    version: CurriculumVersionRow
    topic_ids: list[int]
    subtopics_by_topic: dict[int, list[int]]
    student_id: int
    set_id: int
    run: TrainingSessionRow


def _sequential_taxonomy(
    session: Session, *, topics: int, subtopics_per_topic: int = 1
) -> tuple[CurriculumVersionRow, list[int], dict[int, list[int]]]:
    """``topics`` topics in position order, each with its own subtopics."""
    version = CurriculumVersionRow(
        label="Intro Python v1",
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    topic_ids: list[int] = []
    subtopics_by_topic: dict[int, list[int]] = {}
    for topic_index in range(topics):
        topic = TopicRow(
            curriculum_version_id=version.id, name=f"Topic {topic_index}", position=topic_index
        )
        session.add(topic)
        session.flush()
        topic_ids.append(topic.id)
        ids = []
        for sub_index in range(subtopics_per_topic):
            subtopic = SubtopicRow(
                topic_id=topic.id, name=f"Topic {topic_index} Subtopic {sub_index}", position=sub_index
            )
            session.add(subtopic)
            session.flush()
            ids.append(subtopic.id)
        subtopics_by_topic[topic.id] = ids
    session.commit()
    return version, topic_ids, subtopics_by_topic


def _sequential_bank(
    session: Session, *, topics: int = 2, subtopics_per_topic: int = 1, seed: int = 7, name: str = "Ada"
) -> SequentialBank:
    """Every topic gets one approved question tagged to all of its subtopics."""
    version, topic_ids, subtopics_by_topic = _sequential_taxonomy(
        session, topics=topics, subtopics_per_topic=subtopics_per_topic
    )
    question_ids = [
        _true_false(
            session, version=version, topic_id=topic_id, subtopic_ids=subtopics_by_topic[topic_id]
        ).id
        for topic_id in topic_ids
    ]
    student = StudentRepository(session).add(name)
    frozen = QuestionSetRepository(session).create(
        label="Week 1", question_ids=question_ids, curriculum_version_id=version.id
    )
    run = TrainingSessionRepository(session).create(
        student_id=student.id, set_version_id=frozen.id, rng_seed=seed
    )
    session.commit()
    return SequentialBank(
        version=version,
        topic_ids=topic_ids,
        subtopics_by_topic=subtopics_by_topic,
        student_id=student.id,
        set_id=frozen.id,
        run=run,
    )


class TestSequentialProgression:
    """The roulette pool is scoped to one curriculum topic at a time."""

    def test_the_first_question_comes_from_the_first_topic_only(self, session: Session) -> None:
        bank = _sequential_bank(session, topics=3, subtopics_per_topic=2)
        served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)

        assert served.attempt.subtopic_id in bank.subtopics_by_topic[bank.topic_ids[0]]

    def test_mastering_a_topic_advances_to_the_next_one(self, session: Session) -> None:
        bank = _sequential_bank(session, topics=2)
        StudentStateRepository(session).record_mastery(bank.student_id, bank.topic_ids[0], 0.9)
        session.commit()

        served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)
        assert served.attempt.subtopic_id in bank.subtopics_by_topic[bank.topic_ids[1]]

    def test_a_topic_with_nothing_servable_is_skipped(self, session: Session) -> None:
        version, topic_ids, subtopics_by_topic = _sequential_taxonomy(session, topics=2)
        # Only the second topic gets an approved question; the first is a bank
        # gap the engine must not stall on.
        question = _true_false(
            session,
            version=version,
            topic_id=topic_ids[1],
            subtopic_ids=subtopics_by_topic[topic_ids[1]],
        )
        student = StudentRepository(session).add("Ada")
        frozen = QuestionSetRepository(session).create(
            label="Week 1", question_ids=[question.id], curriculum_version_id=version.id
        )
        run = TrainingSessionRepository(session).create(
            student_id=student.id, set_version_id=frozen.id, rng_seed=1
        )
        session.commit()

        served = AdaptiveTrainingEngine(session).serve_next(run.id)
        assert served.attempt.subtopic_id in subtopics_by_topic[topic_ids[1]]

    def test_finishing_every_topic_ends_the_session(self, session: Session) -> None:
        bank = _sequential_bank(session, topics=2)
        state = StudentStateRepository(session)
        state.record_mastery(bank.student_id, bank.topic_ids[0], 0.9)
        state.record_mastery(bank.student_id, bank.topic_ids[1], 0.9)
        session.commit()

        with pytest.raises(CurriculumCompletedError):
            AdaptiveTrainingEngine(session).serve_next(bank.run.id)
        session.commit()
        assert bank.run.ended_at is not None

    def test_a_set_with_no_curriculum_link_pools_every_topic(self, session: Session) -> None:
        """A set whose curriculum was later deleted keeps the old pooled behavior."""
        bank = _bank(session, difficulty=Difficulty.HARD)
        StudentStateRepository(session).record_mastery(bank.student_id, bank.topic_id, 0.9)
        QuestionSetRepository(session).get(bank.set_id).curriculum_version_id = None
        session.commit()

        served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)
        assert served.attempt.served_difficulty is Difficulty.HARD


class TestServing:
    """Drawing and handing over a question."""

    def test_a_question_is_served_and_recorded(self, session: Session) -> None:
        bank = _bank(session)
        served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)
        session.commit()

        assert served.question.status is QuestionStatus.APPROVED
        assert served.attempt.ordinal == 1
        assert served.attempt.student_id == bank.student_id
        assert served.attempt.subtopic_id == bank.subtopic_ids[0]
        assert served.attempt.score is None
        assert served.resumed is False

    def test_serving_drops_the_questions_priority(self, session: Session) -> None:
        """The fixed rule: a served question sinks to the back of the bank."""
        bank = _bank(session)
        served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)
        session.commit()

        assert served.question.priority == LOWEST_PRIORITY
        assert served.question.times_used == 1

    def test_serving_records_the_mastery_it_decided_from(self, session: Session) -> None:
        bank = _bank(session)
        served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)
        assert served.attempt.mastery_before == pytest.approx(DEFAULT_BKT_PARAMETERS.p_init)

    def test_asking_again_returns_the_open_question(self, session: Session) -> None:
        """Reloading must not abandon the attempt and let a student skip it."""
        bank = _bank(session, questions=3)
        engine = AdaptiveTrainingEngine(session)
        first = engine.serve_next(bank.run.id)
        session.commit()
        again = engine.serve_next(bank.run.id)

        assert again.question.id == first.question.id
        assert again.attempt.id == first.attempt.id
        assert again.resumed is True
        assert StudentAttemptRepository(session).next_ordinal(bank.run.id) == 2

    def test_the_next_question_differs_once_the_first_is_answered(self, session: Session) -> None:
        bank = _bank(session, questions=2)
        engine = AdaptiveTrainingEngine(session)
        first = engine.serve_next(bank.run.id)
        engine.submit_answer(first.attempt.id, "true")
        session.commit()

        second = engine.serve_next(bank.run.id)
        assert second.question.id != first.question.id
        assert second.attempt.ordinal == 2

    def test_reuse_resumes_once_every_question_has_been_seen(self, session: Session) -> None:
        """Seen questions are ranked, not filtered, so the run does not stall."""
        bank = _bank(session, questions=2)
        engine = AdaptiveTrainingEngine(session)
        first = engine.serve_next(bank.run.id)
        engine.submit_answer(first.attempt.id, "true")
        second = engine.serve_next(bank.run.id)
        engine.submit_answer(second.attempt.id, "true")
        session.commit()

        third = engine.serve_next(bank.run.id)
        assert third.question.id in {first.question.id, second.question.id}

    def test_being_unseen_outranks_both_priority_and_usage(self, session: Session) -> None:
        """ADR-041's own key, isolated: the unseen question wins on nothing else.

        ``seen`` is the better candidate by every field of the fixed rule --
        higher priority, fewer uses -- and loses purely because this student has
        already answered it.
        """
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=1)
        seen = _true_false(session, version=version, topic_id=topic_id, subtopic_ids=subtopic_ids)
        unseen = _true_false(session, version=version, topic_id=topic_id, subtopic_ids=subtopic_ids)
        unseen.priority = LOWEST_PRIORITY
        unseen.times_used = 5
        student = StudentRepository(session).add("Ada")
        frozen = QuestionSetRepository(session).create(
            label="Week 1",
            question_ids=[seen.id, unseen.id],
            curriculum_version_id=version.id,
        )
        run = TrainingSessionRepository(session).create(
            student_id=student.id, set_version_id=frozen.id, rng_seed=1
        )
        session.flush()
        StudentAttemptRepository(session).add(
            StudentAttemptRow(
                session_id=run.id,
                student_id=student.id,
                question_id=seen.id,
                ordinal=1,
                subtopic_id=subtopic_ids[0],
                score=100.0,
                answered_at=datetime.now(UTC),
            )
        )
        session.commit()

        served = AdaptiveTrainingEngine(session).serve_next(run.id)
        assert served.question.id == unseen.id

    def test_another_students_usage_does_not_hide_a_question(self, session: Session) -> None:
        bank = _bank(session, questions=1)
        engine = AdaptiveTrainingEngine(session)
        mine = engine.serve_next(bank.run.id)
        engine.submit_answer(mine.attempt.id, "true")
        session.commit()

        other = StudentRepository(session).add("Grace")
        other_run = TrainingSessionRepository(session).create(
            student_id=other.id, set_version_id=bank.set_id, rng_seed=1
        )
        session.commit()

        served = AdaptiveTrainingEngine(session).serve_next(other_run.id)
        assert served.question.id == mine.question.id

    def test_the_same_seed_replays_the_same_draw(self, session: Session) -> None:
        bank = _bank(session, subtopics=3, questions=3, seed=99)
        first = AdaptiveTrainingEngine(session).serve_next(bank.run.id).attempt.subtopic_id
        session.rollback()

        replay = TrainingSessionRepository(session).create(
            student_id=bank.student_id, set_version_id=bank.set_id, rng_seed=99
        )
        session.commit()
        second = AdaptiveTrainingEngine(session).serve_next(replay.id).attempt.subtopic_id
        assert first == second


class TestDifficulty:
    """Difficulty follows BKT topic mastery."""

    def test_low_mastery_is_served_an_easy_question(self, session: Session) -> None:
        bank = _bank(session, difficulty=Difficulty.EASY)
        served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)
        assert served.attempt.requested_difficulty is Difficulty.EASY
        assert served.attempt.served_difficulty is Difficulty.EASY
        assert served.fallback_used is False

    def test_high_mastery_ends_a_single_topic_curriculum_instead_of_escalating(
        self, session: Session
    ) -> None:
        """0.9 mastery would request HARD, but it is also past
        TOPIC_ADVANCE_CEILING, so sequential progression retires the topic
        first -- with only one topic, that ends the run instead (see
        TestSequentialProgression for the multi-topic case).
        """
        bank = _bank(session, difficulty=Difficulty.HARD)
        StudentStateRepository(session).record_mastery(bank.student_id, bank.topic_id, 0.9)
        session.commit()

        with pytest.raises(CurriculumCompletedError):
            AdaptiveTrainingEngine(session).serve_next(bank.run.id)

    def test_an_empty_cell_relaxes_difficulty_and_says_so(self, session: Session) -> None:
        """A bank with gaps must not read as a bank that chose these on purpose."""
        bank = _bank(session, difficulty=Difficulty.MEDIUM)
        served = AdaptiveTrainingEngine(session).serve_next(bank.run.id)

        assert served.attempt.requested_difficulty is Difficulty.EASY
        assert served.attempt.served_difficulty is Difficulty.MEDIUM
        assert served.fallback_used is True

    def test_medium_steps_down_before_it_steps_up(self, session: Session) -> None:
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=1)
        easy = _true_false(
            session,
            version=version,
            topic_id=topic_id,
            subtopic_ids=subtopic_ids,
            difficulty=Difficulty.EASY,
        )
        hard = _true_false(
            session,
            version=version,
            topic_id=topic_id,
            subtopic_ids=subtopic_ids,
            difficulty=Difficulty.HARD,
        )
        student = StudentRepository(session).add("Ada")
        frozen = QuestionSetRepository(session).create(
            label="Week 1",
            question_ids=[easy.id, hard.id],
            curriculum_version_id=version.id,
        )
        run = TrainingSessionRepository(session).create(
            student_id=student.id, set_version_id=frozen.id, rng_seed=1
        )
        # Medium band, but the subtopic holds only easy and hard.
        StudentStateRepository(session).record_mastery(student.id, topic_id, 0.5)
        session.commit()

        served = AdaptiveTrainingEngine(session).serve_next(run.id)
        assert served.attempt.requested_difficulty is Difficulty.MEDIUM
        assert served.attempt.served_difficulty is Difficulty.EASY


class TestScoring:
    """One score, two independent state updates."""

    def test_a_correct_answer_raises_mastery_and_lowers_weakness(self, session: Session) -> None:
        bank = _bank(session)
        engine = AdaptiveTrainingEngine(session)
        served = engine.serve_next(bank.run.id)
        answered = engine.submit_answer(served.attempt.id, "true")
        session.commit()

        assert answered.scored.score == 100.0
        assert answered.mastery_after > answered.mastery_before
        state = StudentStateRepository(session)
        assert state.mastery_for(bank.student_id, bank.topic_id) == answered.mastery_after
        assert (
            state.weaknesses_for(bank.student_id, bank.subtopic_ids)[bank.subtopic_ids[0]]
            < INITIAL_SUBTOPIC_WEAKNESS
        )

    def test_a_wrong_answer_lowers_mastery(self, session: Session) -> None:
        bank = _bank(session)
        engine = AdaptiveTrainingEngine(session)
        served = engine.serve_next(bank.run.id)
        answered = engine.submit_answer(served.attempt.id, "false")
        session.commit()

        assert answered.scored.score == 0.0
        assert answered.mastery_after < answered.mastery_before

    def test_the_attempt_records_what_happened(self, session: Session) -> None:
        bank = _bank(session)
        engine = AdaptiveTrainingEngine(session)
        served = engine.serve_next(bank.run.id)
        engine.submit_answer(served.attempt.id, "true")
        session.commit()

        stored = StudentAttemptRepository(session).get(served.attempt.id)
        assert stored.answer == "true"
        assert stored.score == 100.0
        assert stored.answered_at is not None
        assert stored.mastery_after is not None

    def test_every_subtopic_on_the_question_is_updated(self, session: Session) -> None:
        """A question tagged with three subtopics has measured all three."""
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=3)
        question = _true_false(
            session, version=version, topic_id=topic_id, subtopic_ids=subtopic_ids
        )
        student = StudentRepository(session).add("Ada")
        frozen = QuestionSetRepository(session).create(
            label="Week 1", question_ids=[question.id], curriculum_version_id=version.id
        )
        run = TrainingSessionRepository(session).create(
            student_id=student.id, set_version_id=frozen.id, rng_seed=1
        )
        session.commit()

        engine = AdaptiveTrainingEngine(session)
        served = engine.serve_next(run.id)
        engine.submit_answer(served.attempt.id, "true")
        session.commit()

        weaknesses = StudentStateRepository(session).weaknesses_for(student.id, subtopic_ids)
        assert all(value < INITIAL_SUBTOPIC_WEAKNESS for value in weaknesses.values())

    def test_answering_twice_is_refused(self, session: Session) -> None:
        bank = _bank(session)
        engine = AdaptiveTrainingEngine(session)
        served = engine.serve_next(bank.run.id)
        engine.submit_answer(served.attempt.id, "true")
        session.commit()

        with pytest.raises(DomainRuleError):
            engine.submit_answer(served.attempt.id, "false")

    def test_an_unknown_attempt_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            AdaptiveTrainingEngine(session).submit_answer(404, "true")

    def test_repeated_success_drives_the_subtopic_to_the_floor(self, session: Session) -> None:
        bank = _bank(session, questions=1)
        # Repeated correct answers cross the sequential-advance mastery
        # threshold within a handful of iterations; unlinking the curriculum
        # keeps this test about the weakness floor, not topic progression.
        QuestionSetRepository(session).get(bank.set_id).curriculum_version_id = None
        session.commit()
        engine = AdaptiveTrainingEngine(session)
        for _ in range(30):
            served = engine.serve_next(bank.run.id)
            engine.submit_answer(served.attempt.id, "true")
        session.commit()

        weakness = StudentStateRepository(session).weaknesses_for(
            bank.student_id, bank.subtopic_ids
        )[bank.subtopic_ids[0]]
        assert weakness == MIN_SUBTOPIC_WEAKNESS

    def test_two_students_diverge_on_the_same_bank(self, session: Session) -> None:
        """The point of per-student state."""
        bank = _bank(session, questions=1)
        engine = AdaptiveTrainingEngine(session)
        mine = engine.serve_next(bank.run.id)
        engine.submit_answer(mine.attempt.id, "true")

        other = StudentRepository(session).add("Grace")
        other_run = TrainingSessionRepository(session).create(
            student_id=other.id, set_version_id=bank.set_id, rng_seed=1
        )
        session.commit()
        theirs = engine.serve_next(other_run.id)
        engine.submit_answer(theirs.attempt.id, "false")
        session.commit()

        state = StudentStateRepository(session)
        assert state.mastery_for(bank.student_id, bank.topic_id) > state.mastery_for(
            other.id, bank.topic_id
        )


class TestRefusals:
    """What the engine will not do."""

    def test_a_set_with_nothing_approved_cannot_serve(self, session: Session) -> None:
        version, topic_id, subtopic_ids = _taxonomy(session, subtopics=1)
        rejected = _true_false(
            session, version=version, topic_id=topic_id, subtopic_ids=subtopic_ids
        )
        rejected.status = QuestionStatus.REJECTED
        student = StudentRepository(session).add("Ada")
        frozen = QuestionSetRepository(session).create(
            label="Week 1", question_ids=[rejected.id], curriculum_version_id=version.id
        )
        run = TrainingSessionRepository(session).create(
            student_id=student.id, set_version_id=frozen.id, rng_seed=1
        )
        session.commit()

        with pytest.raises(NoQuestionAvailableError):
            AdaptiveTrainingEngine(session).serve_next(run.id)

    def test_a_session_that_lost_its_set_refuses_to_serve(self, session: Session) -> None:
        """Falling back to the live bank would be a different experiment."""
        bank = _bank(session)
        bank.run.set_version_id = None
        session.commit()

        with pytest.raises(DomainRuleError):
            AdaptiveTrainingEngine(session).serve_next(bank.run.id)

    def test_an_ended_session_refuses_to_serve(self, session: Session) -> None:
        bank = _bank(session)
        TrainingSessionRepository(session).end(bank.run)
        session.commit()

        with pytest.raises(DomainRuleError):
            AdaptiveTrainingEngine(session).serve_next(bank.run.id)

    def test_an_unknown_session_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            AdaptiveTrainingEngine(session).serve_next(404)

    def test_a_tag_pointing_at_a_deleted_subtopic_is_skipped(self, session: Session) -> None:
        """Defensive: a question can outlive one of its subtopic tags.

        The tag still names the subtopic, so the draw can reach it, but there is
        no topic behind it and therefore no mastery to pick a difficulty from.
        The engine drops that subtopic rather than guessing.
        """
        bank = _bank(session, subtopics=1)
        session.query(SubtopicRow).filter(SubtopicRow.id == bank.subtopic_ids[0]).delete()
        session.commit()

        with pytest.raises(NoQuestionAvailableError):
            AdaptiveTrainingEngine(session).serve_next(bank.run.id)
