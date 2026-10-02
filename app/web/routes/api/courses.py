"""Course endpoints: the list a professor picks from after login, and creating one.

A course is the workspace books and taxonomies are created in; every other
professor screen works inside one, naming it with the ``X-Course-Id`` header
(see :mod:`app.web.routes.api.deps`). There is no delete yet: a course owns
books and taxonomies, and what removing one should do to them is undecided.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth.backend import current_active_user
from app.courses.overview import SETUP_STEPS, build_overview
from app.persistence.models import CourseRow, UserRow
from app.persistence.repositories import CourseRepository
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    ActivityEventOut,
    CourseCreate,
    CourseListResponse,
    CourseOut,
    CourseProgressOut,
    CoursesOverviewResponse,
    CourseUpdate,
    MostMissedOut,
    SetupStepOut,
)

router = APIRouter(prefix="/courses", tags=["courses"])

CurrentUser = Annotated[UserRow, Depends(current_active_user)]


@router.get("", response_model=CourseListResponse)
def list_courses(session: DbSession) -> CourseListResponse:
    """Every course, newest first, with what has been built in each."""
    repo = CourseRepository(session)
    counts = repo.content_counts()
    return CourseListResponse(
        courses=[
            CourseOut.from_row(row, counts.get(row.id, (0, 0, 0))) for row in repo.list_all()
        ]
    )


# Declared before "/{course_id}" so the literal path is not parsed as an id.
@router.get("/overview", response_model=CoursesOverviewResponse)
def courses_overview(session: DbSession, user: CurrentUser) -> CoursesOverviewResponse:
    """The course list's dashboard: each course's progress, and recent activity."""
    overview = build_overview(session)
    return CoursesOverviewResponse(
        courses=[
            CourseProgressOut(
                course=CourseOut.from_row(
                    p.course, (p.book_count, p.curriculum_version_count, p.question_count)
                ),
                owner_email=p.owner_email,
                owned_by_you=p.course.owner_id == user.id,
                proposed_curriculum_count=p.proposed_curriculum_count,
                approved_question_count=p.approved_question_count,
                awaiting_review_count=p.awaiting_review_count,
                question_set_count=p.question_set_count,
                student_count=p.student_count,
                coverage=p.coverage,
                avg_mastery=p.avg_mastery,
                most_missed=MostMissedOut(**vars(p.most_missed)) if p.most_missed else None,
                setup=[SetupStepOut(key=key, done=p.setup[key]) for key in SETUP_STEPS],
            )
            for p in overview.courses
        ],
        activity=[ActivityEventOut(**vars(event)) for event in overview.activity],
    )


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(session: DbSession, user: CurrentUser, body: CourseCreate) -> CourseOut:
    """Create an empty course owned by the professor creating it."""
    course = CourseRepository(session).add(
        CourseRow(name=body.name, description=body.description or None, owner_id=user.id)
    )
    session.commit()
    return CourseOut.from_row(course)


@router.get("/{course_id}", response_model=CourseOut)
def get_course(session: DbSession, course_id: int) -> CourseOut:
    repo = CourseRepository(session)
    return CourseOut.from_row(repo.get(course_id), repo.content_counts().get(course_id, (0, 0, 0)))


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(session: DbSession, course_id: int, body: CourseUpdate) -> CourseOut:
    """Rename a course or change its description."""
    repo = CourseRepository(session)
    course = repo.get(course_id)
    if body.name is not None and body.name.strip():
        course.name = body.name.strip()
    if body.description is not None:
        course.description = body.description.strip() or None
    session.commit()
    return CourseOut.from_row(course, repo.content_counts().get(course_id, (0, 0, 0)))
