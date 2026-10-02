"""Shared grounding rules for structured base-question generation."""

from __future__ import annotations

from app.subjects import PYTHON_PROFILE, SubjectProfile


def common_system(profile: SubjectProfile) -> str:
    """The generator's system prompt for one subject.

    Code-only wording (variable names, language features, tests) appears only when
    a chosen question type runs code. The Python profile gives the shipped text.
    """
    if profile.has_code_types:
        return f"""You create one accurate {profile.phrase} assessment question.
Ground the assessed skill in the supplied textbook section. You may use fresh
variable names, literals, and examples, but do not assess an untaught {profile.code_language}
feature or claim the section says something it does not. Keep the requested
difficulty within the taught skill. Return only the requested structured fields;
ensure the reference answer, explanation, and any tests agree with the question."""
    return f"""You create one accurate {profile.phrase} assessment question.
Ground the assessed skill in the supplied textbook section. You may use fresh
names, values, and examples, but do not assess an untaught idea or claim the
section says something it does not. Keep the requested difficulty within the
taught skill. Return only the requested structured fields; ensure the reference
answer and explanation agree with the question."""


COMMON_SYSTEM = common_system(PYTHON_PROFILE)
