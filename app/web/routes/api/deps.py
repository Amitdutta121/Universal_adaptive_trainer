"""Shared dependencies for the JSON API routers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.assessment.catalog import TYPES_BY_ID, course_question_types
from app.errors import DomainRuleError, NotFoundError
from app.persistence.database import get_session
from app.persistence.repositories import CourseRepository
from app.subjects import SubjectProfile, profile_for_course_id

#: Request-scoped database session.
DbSession = Annotated[Session, Depends(get_session)]

#: The header the Instructor Studio sends on every request made inside a course.
COURSE_HEADER = "X-Course-Id"


def _course_scope(
    session: DbSession,
    x_course_id: Annotated[int | None, Header(alias=COURSE_HEADER)] = None,
) -> int | None:
    """The course a request works inside, or ``None`` when it names none.

    A header rather than a path segment so the existing routes keep their paths;
    the Studio derives it from its own ``/courses/{id}/...`` URL. An unknown id is
    a 404 rather than an empty result, so a stale link fails visibly.
    """
    if x_course_id is None:
        return None
    CourseRepository(session).get(x_course_id)
    return x_course_id


#: ``None`` means unscoped -- every course -- which is what callers outside the
#: Studio (scripts, the existing test suite) get by not sending the header.
CourseScope = Annotated[int | None, Depends(_course_scope)]


def _course_profile(session: DbSession, course: CourseScope) -> SubjectProfile:
    """The subject profile of the request's course; Intro Python when it names none."""
    return profile_for_course_id(session, course)


#: What prompts, judge edits and learned instructions in this request follow (ADR-056).
CourseProfile = Annotated[SubjectProfile, Depends(_course_profile)]


def ensure_question_types_allowed(
    session: Session, course: int | None, question_types: Iterable[str]
) -> None:
    """Refuse to generate a question type the course did not choose (ADR-054).

    Unscoped calls (no course) are not checked, which keeps scripts and the existing tests able
    to generate anything, as before courses existed.
    """
    if course is None:
        return
    row = CourseRepository(session).get(course)
    allowed = set(course_question_types(row.subject, row.question_types))
    refused = sorted({str(type_id) for type_id in question_types} - allowed)
    if refused:
        labels = ", ".join(
            TYPES_BY_ID[type_id].label if type_id in TYPES_BY_ID else type_id for type_id in refused
        )
        raise DomainRuleError(
            "This course does not use these question types.",
            detail=f"Not chosen for {row.name}: {labels}.",
        )


def ensure_in_course(row_course_id: int | None, scope: int | None, what: str) -> None:
    """404 when a row fetched by id belongs to a different course than the request's.

    Not-found rather than forbidden: courses are not access control yet (roadmap
    F2), so this only stops one course's screen from showing another's row.
    """
    if scope is not None and row_course_id != scope:
        raise NotFoundError(f"{what} is not part of course {scope}.")
