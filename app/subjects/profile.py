"""What a prompt needs to know about a course's subject (phase 2, decision 4).

Every generator, judge and judge-learning prompt is built from a
:class:`SubjectProfile`: the course's subject preset plus whether any of its chosen
question types runs code. Code-only wording (programs, tests, execution) appears
only when one does. :data:`PYTHON_PROFILE` is what every course was before courses
had subjects, and reproduces the shipped prompts byte for byte
(``tests/golden/python_prompts.json``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.assessment.catalog import (
    LEGACY_SUBJECT,
    QUESTION_TYPES,
    SUBJECTS_BY_ID,
    course_question_types,
)

#: Types marked by running code: the catalogue's "code" group. Any one of them on a
#: course brings in the code-only prompt wording and issue codes.
CODE_TYPES: frozenset[str] = frozenset(spec.id for spec in QUESTION_TYPES if spec.group == "code")

#: Per-preset wording: (phrase in "one accurate <phrase> assessment question",
#: name in "states something false about <name>"). A subject not listed here is
#: named after its course.
_WORDING: dict[str, tuple[str, str]] = {
    "intro_python": ("introductory-Python", "Python"),
    "physics": ("physics", "physics"),
    "biology": ("biology", "biology"),
}


@dataclass(frozen=True)
class SubjectProfile:
    """The subject facts a prompt is a function of."""

    #: Preset id from ``app.assessment.catalog.SUBJECTS`` (``custom`` for a course's own).
    subject_id: str
    #: Learner-facing adjective: "one accurate <phrase> assessment question".
    phrase: str
    #: The subject as a noun: "states something false about <name>".
    name: str
    #: Whether any chosen question type runs code (output prediction, Parsons, ...).
    has_code_types: bool
    #: The course's question types, in catalogue ids.
    question_types: tuple[str, ...] = ()
    #: The course this was read from (``None`` for :data:`PYTHON_PROFILE`).
    course_id: int | None = None

    @property
    def storage_key(self) -> str:
        """The ``subject`` key professor edits and learned rules are stored under (ADR-056).

        A preset is shared by every course using it; a custom subject is one course's own, so
        two custom courses (say "LLMs" and "Art history") never pool what was learned.
        """
        if self.subject_id == "custom" and self.course_id is not None:
            return f"custom:{self.course_id}"
        return self.subject_id

    @property
    def code_language(self) -> str | None:
        """The language the code types run, or ``None`` when none is chosen.

        Every code type needs ``code.python.execute`` (catalogue), so it is Python.
        """
        return "Python" if self.has_code_types else None


class CourseLike(Protocol):
    """The course fields a profile is read from (``CourseRow`` satisfies it)."""

    name: str
    subject: str | None
    question_types: list[str] | None


def _profile(
    subject_id: str,
    question_types: tuple[str, ...],
    course_name: str | None = None,
    course_id: int | None = None,
) -> SubjectProfile:
    if subject_id in _WORDING:
        phrase, name = _WORDING[subject_id]
    else:
        label = (course_name or "").strip() or "course"
        phrase, name = label, label
    return SubjectProfile(
        subject_id=subject_id,
        phrase=phrase,
        name=name,
        has_code_types=any(type_id in CODE_TYPES for type_id in question_types),
        question_types=question_types,
        course_id=course_id,
    )


#: Every course before phase 2: Intro Python with the seven shipped types. Built from
#: the preset's own list (not ``default_types_for``) so importing it never touches the
#: graders or type registries.
PYTHON_PROFILE: SubjectProfile = _profile(
    LEGACY_SUBJECT, SUBJECTS_BY_ID[LEGACY_SUBJECT].default_types
)


def profile_for(course: CourseLike) -> SubjectProfile:
    """The profile of one course.

    A legacy course (no subject) is Intro Python; one that recorded no question
    types keeps its subject's defaults (:func:`course_question_types`). A custom or
    unknown subject is named after the course.
    """
    subject_id = course.subject or LEGACY_SUBJECT
    if subject_id not in SUBJECTS_BY_ID:
        subject_id = "custom"
    types = tuple(course_question_types(subject_id, course.question_types))
    return _profile(subject_id, types, course.name, getattr(course, "id", None))
