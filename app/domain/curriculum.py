"""Curriculum entities: Topic -> Subtopic, grouped into an approvable version.

The curriculum is versioned because question generation is grounded in *approved
curriculum IDs*. Editing an approved curriculum must produce a new version rather
than mutating the one that existing questions point at.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CurriculumStatus


def _now() -> datetime:
    return datetime.now(UTC)


class Subtopic(BaseModel):
    """A single subtopic. Weakness tracking in the adaptive engine is per subtopic."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    topic_id: int | None = None
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    position: int = Field(default=0, ge=0)


class Topic(BaseModel):
    """A topic. BKT mastery is tracked per topic."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    curriculum_version_id: int | None = None
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    subtopics: list[Subtopic] = Field(default_factory=list)


class CurriculumVersion(BaseModel):
    """An immutable-once-approved snapshot of the Topic -> Subtopic structure."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    label: str = Field(min_length=1, max_length=200)
    status: CurriculumStatus = CurriculumStatus.PROPOSED
    created_at: datetime = Field(default_factory=_now)
    approved_at: datetime | None = None
    topics: list[Topic] = Field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        return self.status is CurriculumStatus.APPROVED
