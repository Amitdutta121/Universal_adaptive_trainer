"""Shared dependencies for the JSON API routers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment.catalog import TYPES_BY_ID, course_question_types
from app.auth.backend import current_active_user, current_verified_user
from app.errors import DomainRuleError, NotFoundError
from app.persistence.database import get_session
from app.persistence.models import (
    BookRow,
    BookSectionRow,
    CurriculumVersionRow,
    QuestionRow,
    SubtopicRow,
    TopicRow,
    UserRow,
)
from app.persistence.repositories import BookRepository, CourseRepository, QuestionRepository
from app.subjects import SubjectProfile, profile_for_course_id

#: Request-scoped database session.
DbSession = Annotated[Session, Depends(get_session)]

#: The header the Instructor Studio sends on every request made inside a course.
COURSE_HEADER = "X-Course-Id"


#: The logged-in professor.
CurrentUser = Annotated[UserRow, Depends(current_active_user)]

#: ``dependencies=`` of every route that spends LLM or embedder credit: the account must have
#: verified its email (ADR-061). ``tests/test_registration.py`` lists these routes.
SPENDS_LLM_CREDIT = [Depends(current_verified_user)]


def owned_course(session: Session, user: UserRow, course_id: int) -> int:
    """``course_id`` when ``user`` owns it; otherwise the same 404 as a missing course."""
    CourseRepository(session).get_owned(course_id, user.id)
    return course_id


def _course_scope(
    session: DbSession,
    user: CurrentUser,
    x_course_id: Annotated[int | None, Header(alias=COURSE_HEADER)] = None,
) -> int | None:
    """The course a request works inside, which the professor must own (ADR-058).

    A header rather than a path segment so the existing routes keep their paths;
    the Studio derives it from its own ``/courses/{id}/...`` URL. A missing header is
    refused rather than read as "every course", and a course someone else owns is a
    404 like an unknown one, so a stale or guessed link fails visibly without
    revealing that the course exists.
    """
    if x_course_id is None:
        raise DomainRuleError(
            "This request must name a course.", detail=f"Send the {COURSE_HEADER} header."
        )
    return owned_course(session, user, x_course_id)


#: The request's course, owned by the logged-in professor. Typed ``int | None`` only
#: because the test suite overrides ``_course_scope`` so a call without the header
#: stays unscoped (``tests/conftest.py``); a real request always gets an ``int``.
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

    Together with ``CourseScope`` this is the access check for a row fetched by id: the
    scope is a course the professor owns, and the row must belong to it. Not-found
    rather than forbidden, like an unowned course.
    """
    if scope is not None and row_course_id != scope:
        raise NotFoundError(f"{what} does not exist.")


def question_in_course(session: Session, question_id: int, scope: int | None) -> QuestionRow:
    """The question, or a 404 when it belongs to a different course than the request's."""
    question = QuestionRepository(session).get(question_id)
    version = (
        session.get(CurriculumVersionRow, question.curriculum_version_id)
        if question.curriculum_version_id is not None
        else None
    )
    ensure_in_course(
        version.course_id if version is not None else None, scope, f"Question {question_id}"
    )
    return question


def version_in_course(session: Session, version_id: int, scope: int | None) -> None:
    """404 when a curriculum version named in a body or query belongs to another course."""
    version = session.get(CurriculumVersionRow, version_id)
    if version is None:
        raise NotFoundError(f"Curriculum version {version_id} does not exist.")
    ensure_in_course(version.course_id, scope, f"Curriculum version {version_id}")


def subtopics_in_course(session: Session, subtopic_ids: Iterable[int], scope: int | None) -> None:
    """404 unless every subtopic id belongs to a taxonomy of the request's course."""
    ids = set(subtopic_ids)
    if scope is None or not ids:
        return
    found = set(
        session.scalars(
            select(SubtopicRow.id)
            .join(TopicRow, TopicRow.id == SubtopicRow.topic_id)
            .join(CurriculumVersionRow, CurriculumVersionRow.id == TopicRow.curriculum_version_id)
            .where(SubtopicRow.id.in_(ids), CurriculumVersionRow.course_id == scope)
        )
    )
    if missing := sorted(ids - found):
        raise NotFoundError(f"Subtopic {', '.join(map(str, missing))} does not exist.")


def sections_in_course(session: Session, section_ids: Iterable[int], scope: int | None) -> None:
    """404 unless every book section id belongs to a book of the request's course."""
    ids = set(section_ids)
    if scope is None or not ids:
        return
    found = set(
        session.scalars(
            select(BookSectionRow.id)
            .join(BookRow, BookRow.id == BookSectionRow.book_id)
            .where(BookSectionRow.id.in_(ids), BookRow.course_id == scope)
        )
    )
    if missing := sorted(ids - found):
        listed = ", ".join(map(str, missing))
        raise NotFoundError(f"Section {listed} does not exist.")


def book_in_course(session: Session, book_id: int, scope: int | None) -> None:
    """404 when a book named in a body or query belongs to another course."""
    ensure_in_course(BookRepository(session).get(book_id).course_id, scope, f"Book {book_id}")
