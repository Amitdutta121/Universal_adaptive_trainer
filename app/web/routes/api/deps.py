"""Shared dependencies for the JSON API routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.persistence.database import get_session
from app.persistence.repositories import CourseRepository

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


def ensure_in_course(row_course_id: int | None, scope: int | None, what: str) -> None:
    """404 when a row fetched by id belongs to a different course than the request's.

    Not-found rather than forbidden: courses are not access control yet (roadmap
    F2), so this only stops one course's screen from showing another's row.
    """
    if scope is not None and row_course_id != scope:
        raise NotFoundError(f"{what} is not part of course {scope}.")
