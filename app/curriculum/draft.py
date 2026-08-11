"""Stage C: the proposed curriculum as structured, reviewable entities.

These types are pure and hold no database identity. They are what the pipeline
produces and what the deterministic checks run against, so a proposal is fully
formed and fully checked *before* anything is written -- the same discipline
ingestion applies to book documents (ADR-015).

Every proposed subtopic carries its own provenance: the differing book wordings
that were merged into it, the reason they were judged equivalent, and the
sections that support it. That is not decoration. A professor asked to approve a
knowledge-component model they did not write needs to see what each component was
derived from, and the adaptive engine's weakness dimensions are only as
trustworthy as the evidence behind them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.books import SectionSource
from app.domain.enums import ConceptConfidence


def _now() -> datetime:
    return datetime.now(UTC)


class ProposalWarningCode(StrEnum):
    """Caveats a proposal declares about itself.

    A closed vocabulary so the UI can group them, mirroring how book documents
    declare their own caveats. A proposal that quietly analysed half the sections
    is worse than one that says it did.
    """

    #: The run hit ``curriculum_max_sections`` and did not analyse everything.
    SECTIONS_SKIPPED = "sections_skipped"
    #: A section was longer than the Stage A context budget and was truncated.
    SECTION_TEXT_TRUNCATED = "section_text_truncated"
    #: Stage A failed for one section; the run continued without it.
    SECTION_ANALYSIS_FAILED = "section_analysis_failed"
    #: Stage B returned without placing every candidate into a group.
    CANDIDATES_UNASSIGNED = "candidates_unassigned"
    #: Two groups normalised to the same name and were merged deterministically.
    DUPLICATE_GROUPS_MERGED = "duplicate_groups_merged"


class ProposalWarning(BaseModel):
    """One caveat about how this proposal was produced."""

    model_config = ConfigDict(frozen=True)

    code: ProposalWarningCode
    message: str = Field(min_length=1)
    location: str | None = None

    def __str__(self) -> str:
        return f"{self.message} ({self.location})" if self.location else self.message


class DraftEvidence(BaseModel):
    """One section's contribution to a proposed subtopic."""

    model_config = ConfigDict(from_attributes=True)

    #: The label this section's own analysis used, before normalisation.
    candidate_label: str = Field(min_length=1)
    #: What that analysis said the concept was.
    definition: str = Field(min_length=1)
    #: Short excerpts from the section showing the concept being taught.
    quotes: list[str] = Field(default_factory=list)
    #: Full traceability back to book, chapter, section and pages.
    source: SectionSource

    @property
    def citation(self) -> str:
        return self.source.citation()


class DraftSubtopic(BaseModel):
    """A proposed subtopic: one weakness dimension, with its provenance."""

    model_config = ConfigDict(from_attributes=True)

    stable_id: str = Field(min_length=1)
    #: The stable id of the topic this belongs to. Held explicitly so that an
    #: orphaned or mis-parented subtopic is something the checks can *detect*,
    #: rather than something the nesting makes structurally unsayable.
    topic_stable_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    reason_for_grouping: str = Field(min_length=1)
    confidence: ConceptConfidence
    #: Every distinct book wording that normalised to this subtopic.
    candidate_labels: list[str] = Field(default_factory=list)
    evidence: list[DraftEvidence] = Field(default_factory=list)
    position: int = Field(default=0, ge=0)

    @property
    def section_ids(self) -> list[int]:
        """Distinct supporting section ids, in first-seen order."""
        return list(dict.fromkeys(item.source.section_id for item in self.evidence))

    @property
    def book_ids(self) -> list[int]:
        return list(dict.fromkeys(item.source.book_id for item in self.evidence))

    @property
    def section_count(self) -> int:
        return len(self.section_ids)

    @property
    def book_count(self) -> int:
        return len(self.book_ids)

    @property
    def is_cross_book(self) -> bool:
        """Whether this subtopic consolidates wordings from more than one book."""
        return self.book_count > 1


class DraftTopic(BaseModel):
    """A proposed topic: the unit BKT mastery will be tracked against."""

    model_config = ConfigDict(from_attributes=True)

    stable_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=300)
    #: Derived from the subtopics beneath it, never model-generated -- see
    #: :func:`describe_topic`. A topic description that named skills the topic
    #: does not contain would be a fabrication.
    description: str = Field(min_length=1)
    position: int = Field(default=0, ge=0)
    subtopics: list[DraftSubtopic] = Field(default_factory=list)

    @property
    def section_count(self) -> int:
        sections = {item for sub in self.subtopics for item in sub.section_ids}
        return len(sections)

    @property
    def book_count(self) -> int:
        books = {item for sub in self.subtopics for item in sub.book_ids}
        return len(books)


class ExtractionMetadata(BaseModel):
    """How this proposal was produced, so two proposals stay comparable."""

    model_config = ConfigDict(from_attributes=True)

    #: Provider and model, e.g. "openrouter/deepseek/deepseek-chat". Never a credential.
    generated_by: str = Field(min_length=1)
    stage_a_version: str = Field(min_length=1)
    stage_b_version: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=_now)
    books_analysed: int = Field(default=0, ge=0)
    sections_analysed: int = Field(default=0, ge=0)
    sections_skipped: int = Field(default=0, ge=0)
    candidates_extracted: int = Field(default=0, ge=0)
    groups_returned: int = Field(default=0, ge=0)


class CurriculumDraft(BaseModel):
    """A complete proposed curriculum, before it is persisted."""

    model_config = ConfigDict(from_attributes=True)

    label: str = Field(min_length=1, max_length=200)
    source_book_ids: list[int] = Field(default_factory=list)
    topics: list[DraftTopic] = Field(default_factory=list)
    metadata: ExtractionMetadata
    warnings: list[ProposalWarning] = Field(default_factory=list)

    @property
    def subtopics(self) -> list[DraftSubtopic]:
        return [subtopic for topic in self.topics for subtopic in topic.subtopics]

    @property
    def subtopic_count(self) -> int:
        return len(self.subtopics)

    @property
    def cross_book_subtopic_count(self) -> int:
        """How many subtopics actually merged wordings from several books.

        The headline measure of whether Stage B did anything: a proposal where
        this is zero consolidated nothing across books.
        """
        return sum(1 for subtopic in self.subtopics if subtopic.is_cross_book)


def describe_topic(name: str, subtopics: list[DraftSubtopic]) -> str:
    """Summarise a topic by listing the skills it contains.

    Deliberately derived rather than asked of the model: the honest description
    of a proposed topic is exactly what is under it, and a generated sentence
    could describe coverage the proposal does not actually have.
    """
    if not subtopics:
        return f"{name}. No subtopics were proposed for this topic."
    listed = ", ".join(subtopic.name for subtopic in subtopics)
    return f"{name}. Covers: {listed}."
