"""Student endpoints: enrol a learner, run a training session, read progress.

The student half of the application (ADR-041). Everything a student does goes
through :class:`~app.adaptive.service.AdaptiveTrainingEngine`; this module only
translates between HTTP and that engine, and assembles the read-only progress
view from the repositories.

The two loops stay separate here as everywhere else: nothing in this module
touches judges, reviews or learned instructions, and nothing a student does
feeds professor preference (ADR-001).

This module mixes two audiences, unlike every other router under
``routes/api``: a student reaches ``/api/students`` (enrol),
``/api/students/resume`` (return as an existing learner),
``/api/training-sessions`` (start/serve/answer/end) and ``/api/attempts``
anonymously by link
(``/students/join/session/{id}`` on the frontend), plus the one frozen-set read
that powers the join lobby (``/students/join?set=...``), so those stay public.
Only the professor-facing reads -- listing students, one student's detail and
progress, and listing a student's sessions -- carry
``Depends(current_active_user)``.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status

from app.adaptive import AdaptiveTrainingEngine
from app.auth.backend import current_active_user
from app.coverage import get_prod_question_set
from app.domain.mastery import difficulty_for_mastery, mastery_band
from app.errors import ActiveSessionExistsError, DomainRuleError, NotFoundError
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
    ClassSummaryOut,
    ClassTrendAttemptOut,
    ClassWeaknessCellOut,
    ClassWeaknessStudentOut,
    CreateStudentRequest,
    QuestionSetOut,
    ResumeStudentRequest,
    ServedQuestionOut,
    StartTrainingSessionRequest,
    StudentIdentityOut,
    StudentListResponse,
    StudentOut,
    StudentProgressOut,
    StudentResumeOut,
    StudentRosterRowOut,
    SubtopicWeaknessOut,
    TopicMasteryOut,
    TrainingSessionListResponse,
    TrainingSessionOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["students"])

#: How many recent attempts a progress view carries.
RECENT_ATTEMPTS = 25

#: Default roster page size. The client can ask for up to 100.
ROSTER_PAGE_SIZE = 20

#: Cap on cohort weakness cells returned, matching the client heatmap.
WEAKNESS_CELLS = 48


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; compare them in UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _passes_score(average: float | None, band: str) -> bool:
    if band == "all":
        return True
    if average is None:
        return False
    if band == "lt50":
        return average < 50
    if band == "50to70":
        return 50 <= average < 70
    if band == "70to85":
        return 70 <= average < 85
    if band == "85plus":
        return average >= 85
    return True


def _passes_answered(count: int, band: str) -> bool:
    if band == "all":
        return True
    if band == "0":
        return count == 0
    if band == "1to5":
        return 1 <= count <= 5
    if band == "6to20":
        return 6 <= count <= 20
    if band == "21plus":
        return count >= 21
    return True


def _passes_activity(last_activity: datetime | None, band: str, *, now: datetime) -> bool:
    if band == "all":
        return True
    if last_activity is None:
        return band == "inactive"
    age_days = (now - _aware(last_activity)).total_seconds() / 86400
    if band == "today":
        return age_days < 1
    if band == "last7":
        return age_days <= 7
    if band == "last30":
        return age_days <= 30
    if band == "inactive":
        return age_days > 30
    return True


@router.get("/question-sets/prod", response_model=QuestionSetOut)
def get_prod_classroom(session: DbSession) -> QuestionSetOut:
    """The current production classroom snapshot behind the stable join link."""
    return QuestionSetOut.from_row(get_prod_question_set(session), is_prod=True)


@router.get("/question-sets/{set_version_id}", response_model=QuestionSetOut)
def get_question_set(session: DbSession, set_version_id: int) -> QuestionSetOut:
    """One frozen set, public so an anonymous join link can describe itself."""
    return QuestionSetOut.from_row(QuestionSetRepository(session).get(set_version_id))


@router.get(
    "/students",
    response_model=StudentListResponse,
    dependencies=[Depends(current_active_user)],
)
def list_students(
    session: DbSession,
    search: str = "",
    score: str = "all",
    answered: str = "all",
    activity: str = "all",
    curriculum_version_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(ROSTER_PAGE_SIZE, ge=1, le=100),
) -> StudentListResponse:
    """One page of the roster, filtered server-side (ADR-041 keeps it read-only).

    The score, answered and activity filters run off one grouped pass over the
    attempt table -- :meth:`StudentAttemptRepository.stats_by_student` -- rather
    than a progress fetch per learner, so the cost no longer grows with the
    cohort. ``total`` is the count *after* filtering, so the client can size its
    page controls.

    ``curriculum_version_id`` narrows to students with at least one session on a
    set built from that taxonomy (see
    :meth:`TrainingSessionRepository.student_ids_for_curriculum_version`) -- a
    student is never tagged with a taxonomy directly, only a frozen set is.
    """
    students = StudentRepository(session)
    attempts = StudentAttemptRepository(session)
    stats = attempts.stats_by_student()
    now = datetime.now(UTC)
    allowed_ids = (
        TrainingSessionRepository(session).student_ids_for_curriculum_version(
            curriculum_version_id
        )
        if curriculum_version_id is not None
        else None
    )

    matched = []
    for row in students.search(search):
        if allowed_ids is not None and row.id not in allowed_ids:
            continue
        stat = stats.get(row.id)
        average = stat.average_score if stat else None
        answered_count = stat.answered_count if stat else 0
        last_activity = stat.last_activity_at if stat else None
        if (
            _passes_score(average, score)
            and _passes_answered(answered_count, answered)
            and _passes_activity(last_activity, activity, now=now)
        ):
            matched.append(row)

    start = (page - 1) * page_size
    page_rows = matched[start : start + page_size]
    series = attempts.scored_series_for([row.id for row in page_rows])

    return StudentListResponse(
        students=[
            StudentRosterRowOut(
                id=row.id,
                display_name=row.display_name,
                email=row.email,
                created_at=row.created_at,
                answered_count=stats[row.id].answered_count if row.id in stats else 0,
                average_score=stats[row.id].average_score if row.id in stats else None,
                last_activity_at=stats[row.id].last_activity_at if row.id in stats else None,
                score_series=series.get(row.id, []),
            )
            for row in page_rows
        ],
        total=len(matched),
        page=page,
        page_size=page_size,
    )


@router.get(
    "/students/class-summary",
    response_model=ClassSummaryOut,
    dependencies=[Depends(current_active_user)],
)
def class_summary(session: DbSession, curriculum_version_id: int | None = None) -> ClassSummaryOut:
    """Cohort-wide figures for the roster's aggregate cards.

    Independent of which roster page is open: the class trend graph and the
    weakness heatmap are about the whole class, so they get their own request
    instead of being rebuilt from whatever page of learners happens to be loaded.

    ``curriculum_version_id``, when given, scopes both the trend and the
    heatmap to that taxonomy -- the same filter the roster's own dropdown
    applies to the student list (see :func:`list_students`).
    """
    students = StudentRepository(session)
    attempts = StudentAttemptRepository(session)
    state = StudentStateRepository(session)
    curriculum = CurriculumRepository(session)

    roster = students.search("")
    stats = attempts.stats_by_student()
    scored = attempts.scored_attempts_all(curriculum_version_id)
    weakness_rows = state.list_weakness_all(curriculum_version_id)

    names = {row.id: row.display_name for row in roster}
    answered_by_student = {student_id: stat.answered_count for student_id, stat in stats.items()}
    labels = curriculum.subtopic_labels_for([row.subtopic_id for row in weakness_rows])

    buckets: dict[int, list[tuple[int, float]]] = {}
    for row in weakness_rows:
        buckets.setdefault(row.subtopic_id, []).append((row.student_id, row.weakness))

    cells: list[ClassWeaknessCellOut] = []
    for subtopic_id, entries in buckets.items():
        label = labels.get(subtopic_id, (None, None))
        affected = sorted(
            (
                ClassWeaknessStudentOut(
                    id=student_id,
                    name=names.get(student_id, f"Student {student_id}"),
                    weakness=weakness,
                    answered=answered_by_student.get(student_id, 0),
                )
                for student_id, weakness in entries
            ),
            key=lambda item: item.weakness,
            reverse=True,
        )
        cells.append(
            ClassWeaknessCellOut(
                subtopic_id=subtopic_id,
                subtopic_name=label[0] or f"Subtopic {subtopic_id} (removed)",
                topic_name=label[1] or "—",
                average_weakness=sum(weakness for _, weakness in entries) / len(entries),
                student_count=len(entries),
                affected=affected,
            )
        )
    cells.sort(key=lambda cell: (cell.average_weakness, cell.student_count), reverse=True)

    measured = {student_id for student_id, count in answered_by_student.items() if count}
    measured.update(row.student_id for row in weakness_rows)
    all_scores = [attempt.score for attempt in scored]

    return ClassSummaryOut(
        student_count=len(roster),
        measured_students=len(measured),
        average_score=sum(all_scores) / len(all_scores) if all_scores else None,
        scored_attempts=[
            ClassTrendAttemptOut(
                student_id=attempt.student_id,
                score=attempt.score,
                answered_at=attempt.answered_at,
                created_at=attempt.created_at,
                ordinal=attempt.ordinal,
            )
            for attempt in scored
        ],
        weakness_cells=cells[:WEAKNESS_CELLS],
    )


@router.post("/students", response_model=StudentIdentityOut, status_code=status.HTTP_201_CREATED)
def create_student(session: DbSession, payload: CreateStudentRequest) -> StudentIdentityOut:
    """Enrol a learner.

    Takes a name and a contact email. Names are unique because the picker is by
    name, so a duplicate would attach one learner's mastery to another. That is
    reported as a rule violation rather than left to surface as a database error.
    The email is validated for shape only and not required to be distinct.

    The response carries the learner's ``resume_token``: the browser that
    enrolled them stores it and presents it to ``POST /students/resume`` to come
    back as the same learner instead of colliding on the unique name.
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
    row = students.add(name, email=str(payload.email).strip())
    session.commit()
    logger.info("Enrolled student %s (%s).", row.id, name)
    return StudentIdentityOut.from_row(row)


@router.post("/students/resume", response_model=StudentResumeOut)
def resume_student(session: DbSession, payload: ResumeStudentRequest) -> StudentResumeOut:
    """Recognise a returning browser by its stored token (ADR-041).

    Public, like enrolment: students have no login. An unknown token is a 404 so
    the caller can drop its stale copy and fall back to enrolling; a known token
    returns the learner, plus their one unfinished run if there is one -- against
    *any* classroom set, not only this link's, because a student runs a single
    session at a time (see :func:`start_training_session`) and the join screen has
    to be able to send them back to it whichever link they arrive on.
    """
    student = StudentRepository(session).get_by_resume_token(payload.resume_token)
    if student is None:
        raise NotFoundError("That resume token does not match any learner.")
    # Validates that the classroom link points at a real set, even though the
    # open run below is found without reference to it.
    QuestionSetRepository(session).get(payload.set_version_id)
    open_run = TrainingSessionRepository(session).open_session_for(student.id)
    active = _session_out(session, open_run.id) if open_run is not None else None
    return StudentResumeOut(student=StudentIdentityOut.from_row(student), active_session=active)


@router.get(
    "/students/{student_id}",
    response_model=StudentOut,
    dependencies=[Depends(current_active_user)],
)
def get_student(session: DbSession, student_id: int) -> StudentOut:
    row = StudentRepository(session).get(student_id)
    return StudentOut.from_row(
        row, answered_count=StudentAttemptRepository(session).count_answered(student_id)
    )


@router.get(
    "/students/{student_id}/progress",
    response_model=StudentProgressOut,
    dependencies=[Depends(current_active_user)],
)
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

    A learner may hold only one unfinished session at a time. A second is
    refused with :class:`ActiveSessionExistsError` rather than created, because
    two attempt streams folding scores into the same per-student BKT state
    corrupt the mastery estimate (ADR-041) -- and an accidental double-join (a
    second tab, a re-followed link) is a routine event, not an edge case. The
    client recovers by resuming the session the error names.
    """
    student = StudentRepository(session).get(payload.student_id)
    frozen = QuestionSetRepository(session).get(payload.set_version_id)
    open_run = TrainingSessionRepository(session).open_session_for(student.id)
    if open_run is not None:
        raise ActiveSessionExistsError(
            f"{student.display_name} already has a training session in progress.",
            detail=(
                f"Session {open_run.id} is still open. Finish or leave it before starting "
                "another -- one learner runs one session at a time so a second tab cannot "
                "corrupt the mastery estimate."
            ),
        )
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


@router.get(
    "/training-sessions",
    response_model=TrainingSessionListResponse,
    dependencies=[Depends(current_active_user)],
)
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
