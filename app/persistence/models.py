"""ORM tables.

Deliberately minimal: only the tables the professor content pipeline needs to
exist now. This is *not* an attempt to design the final schema. Columns that
belong to deferred features (extracted book structure, generator artefacts,
student progress) are absent on purpose and will be added with the feature that
needs them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    BookStatus,
    ConceptConfidence,
    CurriculumItemStatus,
    CurriculumStatus,
    Difficulty,
    GeneratorKind,
    QuestionKind,
    QuestionStatus,
    QuestionType,
    ReviewDecision,
    SourceFormat,
    StructureConfidence,
    StructureSource,
)
from app.domain.questions import DEFAULT_PRIORITY
from app.persistence.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BookRow(TimestampMixin, Base):
    """An imported textbook, as declared by its book JSON document."""

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    #: Only populated when the document states an author. Never inferred.
    author: Mapped[str | None] = mapped_column(String(500), default=None)

    original_filename: Mapped[str] = mapped_column(String(500))
    #: Name of the retained file inside the configured upload directory. The
    #: uploaded document is kept so an import is reproducible from its exact input.
    stored_filename: Mapped[str | None] = mapped_column(String(500), default=None)
    source_format: Mapped[SourceFormat] = mapped_column(String(16), default=SourceFormat.BOOK_JSON)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, default=None)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    #: Provenance declared by the document: what it was made from, and by what.
    source_filename: Mapped[str | None] = mapped_column(String(500), default=None)
    producer: Mapped[str | None] = mapped_column(String(200), default=None)

    status: Mapped[BookStatus] = mapped_column(String(32), default=BookStatus.IMPORTED)
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    #: Document-level warnings, JSON-encoded list of objects.
    warnings_json: Mapped[str | None] = mapped_column(Text, default=None)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    chapters: Mapped[list[BookChapterRow]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="BookChapterRow.position",
    )
    # The book owns its sections: a section that belongs to no chapter must still
    # be deleted with the book, so the cascade lives here rather than on chapter.
    sections: Mapped[list[BookSectionRow]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="BookSectionRow.position",
    )


class BookChapterRow(Base):
    """A chapter of a book. ``title`` is NULL when no heading was found."""

    __tablename__ = "book_chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)

    number: Mapped[str | None] = mapped_column(String(32), default=None)
    title: Mapped[str | None] = mapped_column(String(500), default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)
    start_page: Mapped[int | None] = mapped_column(Integer, default=None)
    end_page: Mapped[int | None] = mapped_column(Integer, default=None)
    structure_source: Mapped[StructureSource] = mapped_column(String(32))
    #: Stored rather than derived, because a document may declare a confidence
    #: that differs from the one its source value implies.
    structure_confidence: Mapped[StructureConfidence] = mapped_column(String(16))

    book: Mapped[BookRow] = relationship(back_populates="chapters")
    # Read-only grouping view; the book owns the section rows.
    sections: Mapped[list[BookSectionRow]] = relationship(
        back_populates="chapter",
        order_by="BookSectionRow.position",
        viewonly=True,
    )


class BookSectionRow(Base):
    """One instructional section: the unit generation will cite.

    ``text`` holds the whole section, not a fixed-size chunk. Any chunking for
    model-context reasons happens downstream and is not stored here.
    """

    __tablename__ = "book_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("book_chapters.id", ondelete="CASCADE"), default=None, index=True
    )

    number: Mapped[str | None] = mapped_column(String(32), default=None)
    #: NULL when the document had no heading here. Never a fabricated title.
    title: Mapped[str | None] = mapped_column(String(500), default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)

    text: Mapped[str] = mapped_column(Text, default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    start_page: Mapped[int | None] = mapped_column(Integer, default=None)
    end_page: Mapped[int | None] = mapped_column(Integer, default=None)

    structure_source: Mapped[StructureSource] = mapped_column(String(32))
    structure_confidence: Mapped[StructureConfidence] = mapped_column(String(16))
    warnings_json: Mapped[str | None] = mapped_column(Text, default=None)

    book: Mapped[BookRow] = relationship(back_populates="sections")
    chapter: Mapped[BookChapterRow | None] = relationship(back_populates="sections")


class CurriculumVersionRow(TimestampMixin, Base):
    """A proposed or approved Topic -> Subtopic snapshot."""

    __tablename__ = "curriculum_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[CurriculumStatus] = mapped_column(String(32), default=CurriculumStatus.PROPOSED)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    #: Which books grounded this proposal, JSON-encoded list of book ids. A
    #: professor reviewing a proposal needs to know what it was derived from.
    source_book_ids_json: Mapped[str | None] = mapped_column(Text, default=None)
    #: Provider and model that produced it, e.g. "openrouter/deepseek/deepseek-chat".
    #: Never a credential. Empty for a version not built by the proposer.
    generated_by: Mapped[str | None] = mapped_column(String(200), default=None)
    #: Stage versions, counts and timings, JSON-encoded. Proposals must stay
    #: comparable across changes to the prompts, so the procedure records itself.
    extraction_metadata_json: Mapped[str | None] = mapped_column(Text, default=None)
    #: Caveats about this proposal (sections skipped, candidates the normalizer
    #: dropped). Shown to the professor rather than logged and forgotten.
    warnings_json: Mapped[str | None] = mapped_column(Text, default=None)

    topics: Mapped[list[TopicRow]] = relationship(
        back_populates="curriculum_version",
        cascade="all, delete-orphan",
        order_by="TopicRow.position",
    )


class TopicRow(Base):
    """A topic. BKT mastery will be tracked per topic."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    curriculum_version_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)

    #: Derived from source-declared labels, not from ``name`` -- see
    #: :mod:`app.curriculum.stable_ids`. Renaming a topic must not change its
    #: identity, or the professor's edits would look like new topics.
    stable_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    review_status: Mapped[CurriculumItemStatus] = mapped_column(
        String(16), default=CurriculumItemStatus.PROPOSED
    )

    curriculum_version: Mapped[CurriculumVersionRow] = relationship(back_populates="topics")
    subtopics: Mapped[list[SubtopicRow]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="SubtopicRow.position",
    )


class SubtopicRow(Base):
    """A subtopic. Weakness will be tracked per subtopic.

    The provenance columns exist because a professor cannot review a proposed
    subtopic without seeing what it was derived from: which wordings across which
    books were merged into it, and why.
    """

    __tablename__ = "subtopics"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)

    stable_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    review_status: Mapped[CurriculumItemStatus] = mapped_column(
        String(16), default=CurriculumItemStatus.PROPOSED
    )
    #: The differing book wordings that normalised to this subtopic, JSON list.
    candidate_labels_json: Mapped[str | None] = mapped_column(Text, default=None)
    #: Why those wordings were judged to be the same concept. Auditable prose.
    grouping_reason: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[ConceptConfidence | None] = mapped_column(String(16), default=None)

    topic: Mapped[TopicRow] = relationship(back_populates="subtopics")
    evidence: Mapped[list[SubtopicEvidenceRow]] = relationship(
        back_populates="subtopic",
        cascade="all, delete-orphan",
        order_by="SubtopicEvidenceRow.position",
    )


class SubtopicEvidenceRow(Base):
    """One section that supports a proposed subtopic, with what it showed.

    This is the traceability record for curriculum proposal: every subtopic the
    system invents must point back at real sections of real books. Without it a
    proposed subtopic is an assertion the professor cannot check.
    """

    __tablename__ = "subtopic_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    subtopic_id: Mapped[int] = mapped_column(
        ForeignKey("subtopics.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("book_sections.id", ondelete="CASCADE"), index=True
    )

    #: The label this section's own analysis used, before normalisation.
    candidate_label: Mapped[str] = mapped_column(String(300))
    #: What the section actually teaches, in the analysis's words.
    definition: Mapped[str | None] = mapped_column(Text, default=None)
    #: Short representative excerpts drawn from the section, JSON list.
    quotes_json: Mapped[str | None] = mapped_column(Text, default=None)
    #: Denormalised one-line citation, so listing evidence needs no extra joins.
    citation: Mapped[str] = mapped_column(String(1000), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    subtopic: Mapped[SubtopicRow] = relationship(back_populates="evidence")
    book: Mapped[BookRow] = relationship()
    section: Mapped[BookSectionRow] = relationship()


class QuestionRow(TimestampMixin, Base):
    """A generated question, with its generated original retained."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Grounding in an approved curriculum.
    curriculum_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="SET NULL"), default=None
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), default=None
    )
    subtopic_id: Mapped[int | None] = mapped_column(
        ForeignKey("subtopics.id", ondelete="SET NULL"), default=None
    )

    kind: Mapped[QuestionKind] = mapped_column(String(32), default=QuestionKind.TESTABLE_PROGRAM)
    question_type: Mapped[QuestionType | None] = mapped_column(String(32), default=None)
    difficulty: Mapped[Difficulty] = mapped_column(String(16), default=Difficulty.EASY)
    status: Mapped[QuestionStatus] = mapped_column(String(32), default=QuestionStatus.GENERATED)

    prompt: Mapped[str] = mapped_column(Text)
    reference_solution: Mapped[str | None] = mapped_column(Text, default=None)
    tests: Mapped[str | None] = mapped_column(Text, default=None)

    spec_json: Mapped[str | None] = mapped_column(Text, default=None)
    content_json: Mapped[str | None] = mapped_column(Text, default=None)

    # Retained generated originals -- never overwritten by professor edits.
    original_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    original_reference_solution: Mapped[str | None] = mapped_column(Text, default=None)
    original_tests: Mapped[str | None] = mapped_column(Text, default=None)

    generator_kind: Mapped[GeneratorKind] = mapped_column(String(32), default=GeneratorKind.BASE)
    generator_name: Mapped[str] = mapped_column(String(200), default="unset")
    generator_version: Mapped[str] = mapped_column(String(50), default="0")

    priority: Mapped[int] = mapped_column(Integer, default=DEFAULT_PRIORITY)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    reviews: Mapped[list[ProfessorReviewRow]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class ProfessorReviewRow(TimestampMixin, Base):
    """Append-only professor verdict on a question."""

    __tablename__ = "professor_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    decision: Mapped[ReviewDecision] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    reviewed_generator_name: Mapped[str | None] = mapped_column(String(200), default=None)
    reviewed_generator_version: Mapped[str | None] = mapped_column(String(50), default=None)

    question: Mapped[QuestionRow] = relationship(back_populates="reviews")
