"""Student endpoints: enrol a learner, run a training session, read progress.

The student half of the application (ADR-041). Everything a student does goes
through :class:`~app.adaptive.service.AdaptiveTrainingEngine`; this module only
translates between HTTP and that engine, and assembles the read-only progress
view from the repositories.

The two loops stay separate here as everywhere else: nothing in this module
touches judges, reviews or learned instructions, and nothing a student does
feeds professor preference (ADR-001).
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, status

from app.adaptive import AdaptiveTrainingEngine
from app.domain.mastery import difficulty_for_mastery, mastery_band
from app.errors import DomainRuleError
from app.persistence.repositories import (
    CurriculumRepository,
    QuestionSetRepository,
    StudentAttemptRepository,
    StudentRepository,
    StudentStateRepository,
    TrainingSessionRepository,
)
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    AnsweredOut,
    AnswerRequest,
    AttemptOut,
    CreateStudentRequest,
    ServedQuestionOut,
    StartTrainingSessionRequest,
    StudentListResponse,
    StudentOut,
    StudentProgressOut,
    SubtopicWeaknessOut,
    TopicMasteryOut,
    TrainingSessionListResponse,
    TrainingSessionOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["students"])

#: How many recent attempts a progress view carries.
RECENT_ATTEMPTS = 25


@router.get("/students", response_model=StudentListResponse)
def list_students(session: DbSession) -> StudentListResponse:
    students = StudentRepository(session)
    attempts = StudentAttemptRepository(session)
    rows = students.list_all()
    return StudentListResponse(
        students=[
            StudentOut.from_row(row, answered_count=attempts.count_answered(row.id)) for row in rows
        ],
        total=len(rows),
    )


@router.post("/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(session: DbSession, payload: CreateStudentRequest) -> StudentOut:
    """Enrol a learner.

    Names are unique because the picker is by name, so a duplicate would attach
    one learner's mastery to another. That is reported as a rule violation rather
    than left to surface as a database error.
    """
    students = StudentRepository(session)
    name = payload.display_name.strip()
    if not name:
        raise DomainRuleError("A student needs a name.")
    if students.get_by_name(name) is not None:
        raise DomainRuleError(
            f"A student called {name!r} already exists.",
            detail="Names identify students here, so they have to be distinct.",
        )
    row = students.add(name)
    session.commit()
    logger.info("Enrolled student %s (%s).", row.id, name)
    return StudentOut.from_row(row)


@router.get("/students/{student_id}", response_model=StudentOut)
def get_student(session: DbSession, student_id: int) -> StudentOut:
    row = StudentRepository(session).get(student_id)
    return StudentOut.from_row(
        row, answered_count=StudentAttemptRepository(session).count_answered(student_id)
    )


@router.get("/students/{student_id}/progress", response_model=StudentProgressOut)
def student_progress(session: DbSession, student_id: int) -> StudentProgressOut:
    """Measured mastery, weakness and history for one learner.

    Only what has been scored appears. State rows are created on first touch
    (ADR-041), so a subtopic nobody has been asked about is absent rather than
    shown at a starting value it was never actually assigned.
    """
    student = StudentRepository(session).get(student_id)
    state = StudentStateRepository(session)
    attempts = StudentAttemptRepository(session)
    curriculum = CurriculumRepository(session)

    mastery_rows = state.list_mastery(student_id)
    weakness_rows = state.list_weakness(student_id)
    topic_names = curriculum.topic_names_for([row.topic_id for row in mastery_rows])
    subtopic_labels = curriculum.subtopic_labels_for([row.subtopic_id for row in weakness_rows])

    history = attempts.list_for_student(student_id, limit=RECENT_ATTEMPTS)
    scored = [attempt.score for attempt in history if attempt.score is not None]

    return StudentProgressOut(
        student=StudentOut.from_row(student, answered_count=attempts.count_answered(student_id)),
        answered=attempts.count_answered(student_id),
        average_score=sum(scored) / len(scored) if scored else None,
        topics=[
            TopicMasteryOut(
                topic_id=row.topic_id,
                # A topic deleted from the curriculum leaves its measurement
                # behind. Naming it honestly beats hiding a real observation.
                topic_name=topic_names.get(row.topic_id, f"Topic {row.topic_id} (removed)"),
                p_known=row.p_known,
                band=mastery_band(row.p_known),
                next_difficulty=difficulty_for_mastery(row.p_known),
                observations=row.observations,
            )
            for row in mastery_rows
        ],
        subtopics=[
            SubtopicWeaknessOut(
                subtopic_id=row.subtopic_id,
                subtopic_name=subtopic_labels.get(row.subtopic_id, (None, None))[0]
                or f"Subtopic {row.subtopic_id} (removed)",
                topic_name=subtopic_labels.get(row.subtopic_id, (None, None))[1] or "—",
                weakness=row.weakness,
                observations=row.observations,
            )
            for row in weakness_rows
        ],
        recent_attempts=[AttemptOut.from_row(row) for row in history],
        sessions=[
            TrainingSessionOut.from_row(row, student_name=student.display_name)
            for row in TrainingSessionRepository(session).list_for_student(student_id)
        ],
    )


@router.post(
    "/training-sessions", response_model=TrainingSessionOut, status_code=status.HTTP_201_CREATED
)
def start_training_session(
    session: DbSession, payload: StartTrainingSessionRequest
) -> TrainingSessionOut:
    """Begin a run for one student against one frozen question set (ADR-036).

    The seed is generated here and stored, which is what makes the run
    replayable: every roulette draw derives from it and the question's position.
    """
    student = StudentRepository(session).get(payload.student_id)
    frozen = QuestionSetRepository(session).get(payload.set_version_id)
    row = TrainingSessionRepository(session).create(
        student_id=student.id,
        set_version_id=frozen.id,
        # Bounded to stay comfortably inside a SQLite INTEGER, and only ever used
        # to seed selection -- nothing here is a security decision.
        rng_seed=secrets.randbelow(2**31),
    )
    session.commit()
    logger.info(
        "Started training session %s for student %s on set %s.", row.id, student.id, frozen.id
    )
    return TrainingSessionOut.from_row(
        row, student_name=student.display_name, set_label=frozen.label
    )


@router.get("/training-sessions", response_model=TrainingSessionListResponse)
def list_training_sessions(session: DbSession, student_id: int) -> TrainingSessionListResponse:
    student = StudentRepository(session).get(student_id)
    rows = TrainingSessionRepository(session).list_for_student(student_id)
    return TrainingSessionListResponse(
        sessions=[
            TrainingSessionOut.from_row(row, student_name=student.display_name) for row in rows
        ],
        total=len(rows),
    )


@router.get("/training-sessions/{training_session_id}", response_model=TrainingSessionOut)
def get_training_session(session: DbSession, training_session_id: int) -> TrainingSessionOut:
    return _session_out(session, training_session_id)


@router.get("/training-sessions/{training_session_id}/next", response_model=ServedQuestionOut)
def next_question(session: DbSession, training_session_id: int) -> ServedQuestionOut:
    """Serve the next question.

    Not idempotent in the HTTP sense -- it writes an attempt row and lowers the
    served question's priority -- but it *is* idempotent while a question is
    outstanding: asking again returns the same one rather than drawing another.
    A GET is still the honest verb, because what a client wants here is the
    session's current question.
    """
    served = AdaptiveTrainingEngine(session).serve_next(training_session_id)
    session.commit()
    subtopic_name = None
    if served.attempt.subtopic_id is not None:
        labels = CurriculumRepository(session).subtopic_labels_for([served.attempt.subtopic_id])
        subtopic_name = labels.get(served.attempt.subtopic_id, (None, None))[0]
    return ServedQuestionOut.from_served(served, subtopic_name=subtopic_name)


@router.post("/attempts/{attempt_id}/answer", response_model=AnsweredOut)
def answer_attempt(session: DbSession, attempt_id: int, payload: AnswerRequest) -> AnsweredOut:
    """Score a submitted answer and fold it into the student's state."""
    try:
        result = AdaptiveTrainingEngine(session).submit_answer(attempt_id, payload.answer)
    except Exception:
        session.rollback()
        raise
    session.commit()
    return AnsweredOut.from_result(result)


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(session: DbSession, attempt_id: int) -> AttemptOut:
    return AttemptOut.from_row(StudentAttemptRepository(session).get(attempt_id))


@router.post("/training-sessions/{training_session_id}/end", response_model=TrainingSessionOut)
def end_training_session(session: DbSession, training_session_id: int) -> TrainingSessionOut:
    repository = TrainingSessionRepository(session)
    repository.end(repository.get(training_session_id))
    session.commit()
    return _session_out(session, training_session_id)


def _session_out(session: DbSession, training_session_id: int) -> TrainingSessionOut:
    row = TrainingSessionRepository(session).get(training_session_id)
    student = StudentRepository(session).get(row.student_id)
    label = None
    if row.set_version_id is not None:
        label = QuestionSetRepository(session).get(row.set_version_id).label
    return TrainingSessionOut.from_row(row, student_name=student.display_name, set_label=label)
