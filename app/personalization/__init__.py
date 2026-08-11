"""Personalization boundary (professor preference learning).

Responsibility
    Turn accumulated professor feedback into a preference profile, then into a
    *personalized* generator that produces questions closer to what this
    professor approves. Later, use the accumulated feedback to optimize the
    generator itself.

Status
    **Not implemented in this task.** Only the seam exists.

Key rules
    * Input is professor feedback only. Student performance belongs to the
      separate student-adaptation loop and must not leak in here.
    * A personalized generator is always versioned and always distinguishable
      from the base generator (see :mod:`app.generation`), so the two can be
      compared rather than silently swapped.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.feedback``,
    ``app.generation`` (for :class:`~app.generation.GeneratorDescriptor`),
    ``app.llm``, ``app.persistence``.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.errors import FeatureNotAvailableError


class ProfessorPreferenceProfile(BaseModel):
    """A professor's learned preferences.

    The shape is intentionally thin: it will be defined by what the review data
    actually supports, not guessed in advance.
    """

    professor_id: int
    #: How many reviews the profile was derived from. Zero means "no signal yet".
    review_count: int = Field(default=0, ge=0)
    #: Version of the profile-building procedure, so profiles stay comparable.
    profile_version: str = "0"

    @property
    def has_signal(self) -> bool:
        return self.review_count > 0


class PreferenceLearner(Protocol):
    """Builds a preference profile from stored professor feedback."""

    def build_profile(self, professor_id: int) -> ProfessorPreferenceProfile: ...


class NullPreferenceLearner:
    """Placeholder learner. Raises rather than returning an empty profile."""

    def build_profile(self, professor_id: int) -> ProfessorPreferenceProfile:
        raise FeatureNotAvailableError(
            "Professor preference learning is not implemented yet.",
            detail=f"Requested profile for professor {professor_id}.",
        )


def get_preference_learner() -> PreferenceLearner:
    """Return the configured learner. Currently always the null implementation."""
    return NullPreferenceLearner()
