"""The course list's dashboard: per-course progress and a recent-activity feed.

Everything here is read from rows that already exist; nothing is stored for it.
A figure the data cannot support (no taxonomy yet, no student has answered)
comes back as ``None`` rather than as a zero that would read as a measurement.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.coverage import build_coverage_report
from app.domain.enums import CurriculumStatus, QuestionStatus, ReviewDecision
from app.persistence.models import (
    BookRow,
    BookSectionRow,
    CourseRow,
    CurriculumVersionRow,
    ProfessorReviewRow,
    QuestionRow,
    QuestionSetVersionRow,
    StudentAttemptRow,
    StudentTopicMasteryRow,
    SubtopicRow,
    TopicRow,
    TrainingSessionRow,
    UserRow,
)
from app.persistence.repositories import (
    CourseRepository,
    CurriculumRepository,
    QuestionRepository,
    questions_in_course,
)

#: Below this many answers a subtopic's miss rate is noise, not a finding.
MIN_ATTEMPTS_FOR_MISS_RATE = 5
#: ``StudentAttemptRow.score`` is a percentage: 0 to 100.
MAX_SCORE = 100.0
#: How many events the activity feed shows.
ACTIVITY_LIMIT = 8

#: The order a course is built in. Each step is done when the data says so.
SETUP_STEPS = ("materials", "taxonomy", "coverage", "review", "question_set", "classes")


@dataclass
class MostMissed:
    subtopic: str
    topic: str
    miss_rate: float
    attempts: int


@dataclass
class CourseProgress:
    course: CourseRow
    owner_email: str | None
    book_count: int
    curriculum_version_count: int
    proposed_curriculum_count: int
    question_count: int
    approved_question_count: int
    awaiting_review_count: int
    question_set_count: int
    student_count: int
    #: Share of the approved taxonomy's subtopic x difficulty cells that are ready.
    coverage: float | None
    avg_mastery: float | None
    most_missed: MostMissed | None
    setup: dict[str, bool] = field(default_factory=dict)


@dataclass
class ActivityEvent:
    kind: str
    text: str
    at: datetime
    course_id: int | None
    course_name: str | None


@dataclass
class CoursesOverview:
    courses: list[CourseProgress]
    activity: list[ActivityEvent]


def build_overview(session: Session, *, owner_id: uuid.UUID | None = None) -> CoursesOverview:
    """Progress and recent activity for every course, or only ``owner_id``'s."""
    courses = CourseRepository(session).list_all(owner_id=owner_id)
    owners = _owner_emails(session, {c.owner_id for c in courses if c.owner_id is not None})
    return CoursesOverview(
        courses=[_progress(session, course, owners.get(course.owner_id)) for course in courses],
        activity=_activity(session, {course.id: course.name for course in courses}),
    )


def _owner_emails(session: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID | None, str]:
    if not ids:
        return {}
    rows = session.execute(select(UserRow.id, UserRow.email).where(UserRow.id.in_(ids)))
    return dict(rows.all())


def _count(session: Session, stmt: Select[tuple[int]]) -> int:
    return session.scalar(stmt) or 0


def _progress(session: Session, course: CourseRow, owner_email: str | None) -> CourseProgress:
    course_id = course.id
    version_ids = select(CurriculumVersionRow.id).where(CurriculumVersionRow.course_id == course_id)
    questions = QuestionRepository(session)

    approved_questions = _count(
        session,
        select(func.count())
        .select_from(QuestionRow)
        .where(questions_in_course(course_id), QuestionRow.status == QuestionStatus.APPROVED),
    )
    set_ids = select(QuestionSetVersionRow.id).where(
        QuestionSetVersionRow.curriculum_version_id.in_(version_ids)
    )
    student_ids = (
        select(TrainingSessionRow.student_id)
        .where(TrainingSessionRow.set_version_id.in_(set_ids))
        .distinct()
    )
    student_count = _count(session, select(func.count()).select_from(student_ids.subquery()))

    approved = CurriculumRepository(session).get_approved(course_id=course_id)
    coverage: float | None = None
    avg_mastery: float | None = None
    most_missed: MostMissed | None = None
    if approved is not None:
        report = build_coverage_report(session, course_id=course_id)
        if report.total_cells:
            coverage = report.ready_cells / report.total_cells
        topic_ids = select(TopicRow.id).where(TopicRow.curriculum_version_id == approved.id)
        avg_mastery = session.scalar(
            select(func.avg(StudentTopicMasteryRow.p_known)).where(
                StudentTopicMasteryRow.topic_id.in_(topic_ids),
                StudentTopicMasteryRow.student_id.in_(student_ids),
                StudentTopicMasteryRow.observations > 0,
            )
        )
        most_missed = _most_missed(session, approved.id)

    book_count = _count(
        session, select(func.count()).select_from(BookRow).where(BookRow.course_id == course_id)
    )
    question_set_count = _count(session, select(func.count()).select_from(set_ids.subquery()))
    setup = {
        "materials": book_count > 0,
        "taxonomy": approved is not None,
        "coverage": coverage is not None and coverage >= 1.0,
        "review": approved_questions > 0,
        "question_set": question_set_count > 0,
        "classes": student_count > 0,
    }
    return CourseProgress(
        course=course,
        owner_email=owner_email,
        book_count=book_count,
        curriculum_version_count=CurriculumRepository(session).count(course_id=course_id),
        proposed_curriculum_count=_count(
            session,
            select(func.count())
            .select_from(CurriculumVersionRow)
            .where(
                CurriculumVersionRow.course_id == course_id,
                CurriculumVersionRow.status == CurriculumStatus.PROPOSED,
            ),
        ),
        question_count=questions.count(course_id=course_id),
        approved_question_count=approved_questions,
        awaiting_review_count=questions.count_reviewable(course_id=course_id)
        - questions.count_reviewed(course_id=course_id),
        question_set_count=question_set_count,
        student_count=student_count,
        coverage=coverage,
        avg_mastery=avg_mastery,
        most_missed=most_missed,
        setup=setup,
    )


def _most_missed(session: Session, version_id: int) -> MostMissed | None:
    """The subtopic students miss most often in this taxonomy, if enough have answered.

    The miss rate is one minus the mean score, so partial credit counts as part-missed.
    """
    stmt = (
        select(
            SubtopicRow.name,
            TopicRow.name,
            func.avg(StudentAttemptRow.score),
            func.count(StudentAttemptRow.id),
        )
        .join(SubtopicRow, SubtopicRow.id == StudentAttemptRow.subtopic_id)
        .join(TopicRow, TopicRow.id == SubtopicRow.topic_id)
        .where(
            TopicRow.curriculum_version_id == version_id,
            StudentAttemptRow.score.is_not(None),
        )
        .group_by(SubtopicRow.id, SubtopicRow.name, TopicRow.name)
        .having(func.count(StudentAttemptRow.id) >= MIN_ATTEMPTS_FOR_MISS_RATE)
        .order_by(func.avg(StudentAttemptRow.score))
        .limit(1)
    )
    row = session.execute(stmt).first()
    if row is None:
        return None
    subtopic, topic, mean_score, attempts = row
    return MostMissed(
        subtopic=subtopic,
        topic=topic,
        miss_rate=1.0 - float(mean_score) / MAX_SCORE,
        attempts=attempts,
    )


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _activity(session: Session, course_names: dict[int, str]) -> list[ActivityEvent]:
    """The newest things that happened in ``course_names``' courses, newest first."""
    events: list[ActivityEvent] = []
    course_ids = list(course_names)

    def add(kind: str, text: str, at: datetime | None, course_id: int | None) -> None:
        if at is not None:
            events.append(
                ActivityEvent(kind, text, at, course_id, course_names.get(course_id or -1))
            )

    section_counts = dict(
        session.execute(
            select(BookSectionRow.book_id, func.count()).group_by(BookSectionRow.book_id)
        ).all()
    )
    for book in session.scalars(
        select(BookRow)
        .where(BookRow.course_id.in_(course_ids))
        .order_by(BookRow.created_at.desc())
        .limit(ACTIVITY_LIMIT)
    ):
        sections = _plural(section_counts.get(book.id, 0), "section")
        add("book", f"Imported {book.title} ({sections})", book.created_at, book.course_id)

    for version in session.scalars(
        select(CurriculumVersionRow)
        .options(selectinload(CurriculumVersionRow.topics))
        .where(CurriculumVersionRow.course_id.in_(course_ids))
        .order_by(CurriculumVersionRow.created_at.desc(), CurriculumVersionRow.id.desc())
        .limit(ACTIVITY_LIMIT)
    ):
        topics = version.topics
        subtopics = sum(len(topic.subtopics) for topic in topics)
        add(
            "taxonomy",
            f"Added taxonomy {version.label}: {_plural(len(topics), 'topic')}, "
            f"{_plural(subtopics, 'subtopic')}",
            version.created_at,
            version.course_id,
        )

    for qset, course_id in session.execute(
        select(QuestionSetVersionRow, CurriculumVersionRow.course_id)
        .outerjoin(
            CurriculumVersionRow,
            CurriculumVersionRow.id == QuestionSetVersionRow.curriculum_version_id,
        )
        .where(CurriculumVersionRow.course_id.in_(course_ids))
        .order_by(QuestionSetVersionRow.created_at.desc())
        .limit(ACTIVITY_LIMIT)
    ):
        add(
            "question_set",
            f"Froze question set “{qset.label}” ({_plural(qset.question_count, 'question')})",
            qset.created_at,
            course_id,
        )

    # Reviews and joins come in bursts, so one event per course per day reads
    # better than one per row.
    reviews: dict[tuple[int | None, str], list] = defaultdict(list)
    for decision, at, course_id in session.execute(
        select(
            ProfessorReviewRow.decision,
            ProfessorReviewRow.created_at,
            CurriculumVersionRow.course_id,
        )
        .join(QuestionRow, QuestionRow.id == ProfessorReviewRow.question_id)
        .outerjoin(
            CurriculumVersionRow, CurriculumVersionRow.id == QuestionRow.curriculum_version_id
        )
        .where(CurriculumVersionRow.course_id.in_(course_ids))
        .order_by(ProfessorReviewRow.created_at.desc())
        .limit(500)
    ):
        reviews[(course_id, at.date().isoformat())].append((decision, at))
    for (course_id, _day), rows in reviews.items():
        # EDIT is approved-with-changes (ReviewDecision's own definition).
        approved = sum(
            1 for decision, _ in rows if decision in (ReviewDecision.APPROVE, ReviewDecision.EDIT)
        )
        text = f"Reviewed {_plural(len(rows), 'question')}"
        if approved:
            text += f", approved {approved}"
        add("review", text, max(at for _, at in rows), course_id)

    first_sessions = (
        select(
            TrainingSessionRow.student_id,
            CurriculumVersionRow.course_id,
            func.min(TrainingSessionRow.created_at).label("joined_at"),
        )
        .join(QuestionSetVersionRow, QuestionSetVersionRow.id == TrainingSessionRow.set_version_id)
        .join(
            CurriculumVersionRow,
            CurriculumVersionRow.id == QuestionSetVersionRow.curriculum_version_id,
        )
        .where(CurriculumVersionRow.course_id.in_(course_ids))
        .group_by(TrainingSessionRow.student_id, CurriculumVersionRow.course_id)
    )
    joins: dict[tuple[int | None, str], list[datetime]] = defaultdict(list)
    for _student, course_id, joined_at in session.execute(first_sessions):
        joins[(course_id, joined_at.date().isoformat())].append(joined_at)
    for (course_id, _day), times in joins.items():
        add("students", f"{_plural(len(times), 'student')} joined", max(times), course_id)

    events.sort(key=lambda event: _aware(event.at), reverse=True)
    return events[:ACTIVITY_LIMIT]


def _aware(at: datetime) -> datetime:
    """SQLite hands back naive datetimes for rows written as UTC; compare them as UTC."""
    return at if at.tzinfo is not None else at.replace(tzinfo=UTC)
