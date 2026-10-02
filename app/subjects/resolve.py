"""Find the subject profile for whatever a request or a question belongs to (phase 2, S3).

Questions reach their course through their curriculum version, books and versions carry
``course_id`` directly. Anything with no course (pre-course rows, calls without a course header)
is Intro Python, which is what every row was before courses existed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.persistence.models import CourseRow, CurriculumVersionRow
from app.subjects.profile import PYTHON_PROFILE, SubjectProfile, profile_for


def profile_for_course_id(session: Session, course_id: int | None) -> SubjectProfile:
    if course_id is None:
        return PYTHON_PROFILE
    course = session.get(CourseRow, course_id)
    return PYTHON_PROFILE if course is None else profile_for(course)


def profile_for_version(session: Session, curriculum_version_id: int | None) -> SubjectProfile:
    if curriculum_version_id is None:
        return PYTHON_PROFILE
    version = session.get(CurriculumVersionRow, curriculum_version_id)
    return PYTHON_PROFILE if version is None else profile_for_course_id(session, version.course_id)


def storage_keys_by_version(session: Session, version_ids: set[int]) -> dict[int, str]:
    """``{curriculum_version_id: storage key}`` (see :attr:`SubjectProfile.storage_key`).

    A version with no course, or a missing one, is absent and so counts as Intro Python.
    """
    if not version_ids:
        return {}
    keys: dict[int, str] = {}
    profiles: dict[int, SubjectProfile] = {}
    for version in session.query(CurriculumVersionRow).filter(
        CurriculumVersionRow.id.in_(version_ids)
    ):
        if version.course_id is None:
            continue
        if version.course_id not in profiles:
            profiles[version.course_id] = profile_for_course_id(session, version.course_id)
        keys[version.id] = profiles[version.course_id].storage_key
    return keys


def key_of_version(keys: dict[int, str], curriculum_version_id: int | None) -> str:
    """The storage key for one version, Intro Python when it has no course."""
    if curriculum_version_id is None:
        return PYTHON_PROFILE.storage_key
    return keys.get(curriculum_version_id, PYTHON_PROFILE.storage_key)


__all__ = [
    "key_of_version",
    "profile_for_course_id",
    "profile_for_version",
    "storage_keys_by_version",
]
