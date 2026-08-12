"""ORM tables.

Deliberately minimal: only the tables the professor content pipeline needs to
exist now. This is *not* an attempt to design the final schema. Columns that
belong to deferred features (extracted book structure, generator artefacts,
student progress) are absent on purpose and will be added with the feature that
needs them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.books import ExtractionWarning
from app.domain.enums import (
    BookStatus,
    ConceptConfidence,
    CurriculumItemStatus,
    CurriculumStatus,
    Difficulty,
    EvaluationTrigger,
    GeneratorKind,
    JudgeBatchStatus,
    PreferenceCategory,
    PreferenceConfirmationState,
    QuestionKind,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
    SourceFormat,
    StructureConfidence,
    StructureSource,
)
from app.domain.questions import DEFAULT_PRIORITY, QuestionValidationReport
from app.persistence.database import Base
from app.persistence.types import (
    EnumList,
    JsonList,
    JsonObject,
    PydanticList,
    PydanticObject,
    StrEnumType,
)


def _now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


#: JSON-bearing attributes name their database column explicitly (the first
#: positional argument to ``mapped_column``) so the attribute can read as what it
#: holds -- ``question.content`` is a ``dict`` -- while the stored column keeps
#: its original ``*_json`` name. Nothing about an existing database file changes.


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
    source_format: Mapped[SourceFormat] = mapped_column(
        StrEnumType(SourceFormat, 16), default=SourceFormat.BOOK_JSON
    )
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, default=None)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    #: Provenance declared by the document: what it was made from, and by what.
    source_filename: Mapped[str | None] = mapped_column(String(500), default=None)
    producer: Mapped[str | None] = mapped_column(String(200), default=None)

    status: Mapped[BookStatus] = mapped_column(
        StrEnumType(BookStatus, 32), default=BookStatus.IMPORTED
    )
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    #: Document-level warnings declared by the imported document.
    warnings: Mapped[list[ExtractionWarning]] = mapped_column(
        "warnings_json", PydanticList(ExtractionWarning), default=list, nullable=True
    )
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
    structure_source: Mapped[StructureSource] = mapped_column(StrEnumType(StructureSource, 32))
    #: Stored rather than derived, because a document may declare a confidence
    #: that differs from the one its source value implies.
    structure_confidence: Mapped[StructureConfidence] = mapped_column(
        StrEnumType(StructureConfidence, 16)
    )

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

    structure_source: Mapped[StructureSource] = mapped_column(StrEnumType(StructureSource, 32))
    structure_confidence: Mapped[StructureConfidence] = mapped_column(
        StrEnumType(StructureConfidence, 16)
    )
    warnings: Mapped[list[ExtractionWarning]] = mapped_column(
        "warnings_json", PydanticList(ExtractionWarning), default=list, nullable=True
    )

    book: Mapped[BookRow] = relationship(back_populates="sections")
    chapter: Mapped[BookChapterRow | None] = relationship(back_populates="sections")


class CurriculumVersionRow(TimestampMixin, Base):
    """A proposed or approved Topic -> Subtopic snapshot."""

    __tablename__ = "curriculum_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[CurriculumStatus] = mapped_column(
        StrEnumType(CurriculumStatus, 32), default=CurriculumStatus.PROPOSED
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    #: Which books grounded this proposal. A professor reviewing a proposal
    #: needs to know what it was derived from.
    source_book_ids: Mapped[list[int]] = mapped_column(
        "source_book_ids_json", JsonList, default=list, nullable=True
    )
    #: Provider and model that produced it, e.g. "openrouter/deepseek/deepseek-chat".
    #: Never a credential. Empty for a version not built by the proposer.
    generated_by: Mapped[str | None] = mapped_column(String(200), default=None)
    #: Stage versions and counts retained from the removed LLM proposal
    #: pipeline. Kept as a plain object because its shape belongs to
    #: :mod:`app.curriculum.display`, which persistence must not import.
    extraction_metadata: Mapped[dict | None] = mapped_column(
        "extraction_metadata_json", JsonObject, default=None
    )
    #: Caveats about this proposal (sections skipped, candidates the normalizer
    #: dropped). Shown to the professor rather than logged and forgotten.
    warnings: Mapped[list[dict]] = mapped_column(
        "warnings_json", JsonList, default=list, nullable=True
    )

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
        StrEnumType(CurriculumItemStatus, 16), default=CurriculumItemStatus.PROPOSED
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
        StrEnumType(CurriculumItemStatus, 16), default=CurriculumItemStatus.PROPOSED
    )
    #: The differing book wordings that normalised to this subtopic.
    candidate_labels: Mapped[list[str]] = mapped_column(
        "candidate_labels_json", JsonList, default=list, nullable=True
    )
    #: Why those wordings were judged to be the same concept. Auditable prose.
    grouping_reason: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[ConceptConfidence | None] = mapped_column(
        StrEnumType(ConceptConfidence, 16), default=None
    )

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
    #: Short representative excerpts drawn from the section.
    quotes: Mapped[list[str]] = mapped_column("quotes_json", JsonList, default=list, nullable=True)
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

    kind: Mapped[QuestionKind] = mapped_column(
        StrEnumType(QuestionKind, 32), default=QuestionKind.TESTABLE_PROGRAM
    )
    question_type: Mapped[QuestionType | None] = mapped_column(
        StrEnumType(QuestionType, 32), default=None
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        StrEnumType(Difficulty, 16), default=Difficulty.EASY
    )
    status: Mapped[QuestionStatus] = mapped_column(
        StrEnumType(QuestionStatus, 32), default=QuestionStatus.GENERATED
    )

    prompt: Mapped[str] = mapped_column(Text)
    reference_solution: Mapped[str | None] = mapped_column(Text, default=None)
    tests: Mapped[str | None] = mapped_column(Text, default=None)

    #: The frozen ``QuestionSpec`` this question was generated from.
    spec: Mapped[dict | None] = mapped_column("spec_json", JsonObject, default=None)
    #: The typed draft plus its grounding metadata (``sources``, ``model``).
    content: Mapped[dict | None] = mapped_column("content_json", JsonObject, default=None)
    validation_report: Mapped[QuestionValidationReport | None] = mapped_column(
        "validation_report_json", PydanticObject(QuestionValidationReport), default=None
    )
    #: Advisory judge output. A plain object because its shape belongs to
    #: :mod:`app.evaluation`, which persistence must not import.
    pedagogical_eval: Mapped[dict | None] = mapped_column(
        "pedagogical_eval_json", JsonObject, default=None
    )

    # Retained generated originals -- never overwritten by professor edits.
    original_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    original_reference_solution: Mapped[str | None] = mapped_column(Text, default=None)
    original_tests: Mapped[str | None] = mapped_column(Text, default=None)

    generator_kind: Mapped[GeneratorKind] = mapped_column(
        StrEnumType(GeneratorKind, 32), default=GeneratorKind.BASE
    )
    generator_name: Mapped[str] = mapped_column(String(200), default="unset")
    generator_version: Mapped[str] = mapped_column(String(50), default="0")

    priority: Mapped[int] = mapped_column(Integer, default=DEFAULT_PRIORITY)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    personalization_context: Mapped[dict | None] = mapped_column(
        "personalization_context_json", JsonObject, default=None
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    reviews: Mapped[list[ProfessorReviewRow]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    #: Append-only judge history. ``pedagogical_eval`` above stays the current
    #: one; these are every evaluation this question has ever received.
    evaluations: Mapped[list[QuestionEvaluationRow]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionEvaluationRow.created_at.desc(), QuestionEvaluationRow.id.desc()",
    )


class QuestionEvaluationRow(TimestampMixin, Base):
    """One pedagogical evaluation of a question, retained forever (ADR-030).

    ``questions.pedagogical_eval_json`` holds only the *current* evaluation, so
    re-judging a question used to overwrite what the judge said the first time.
    This table is the append-only history behind that single value: every
    evaluation ever recorded, whichever run produced it.

    The four denormalised columns (``judge_model``, ``rubric_version``,
    ``eval_status``, ``advisory_status``) are plain strings rather than mapped
    enums because their vocabularies belong to :mod:`app.evaluation`, which
    persistence must not import (ADR-026). They are copies of values inside
    ``evaluation``, kept so a run can be summarised without decoding every blob.
    """

    __tablename__ = "question_evaluations"
    __table_args__ = (
        # One evaluation per question per run. This is what makes re-polling a
        # completed batch a no-op instead of a second set of history rows.
        UniqueConstraint("run_id", "question_id", name="uq_question_evaluations_run_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    #: The full evaluation, in the shape :mod:`app.evaluation` writes and reads.
    evaluation: Mapped[dict | None] = mapped_column(
        "evaluation_json", JsonObject, default=None, nullable=True
    )

    judge_model: Mapped[str | None] = mapped_column(String(200), default=None)
    rubric_version: Mapped[str | None] = mapped_column(String(50), default=None)
    eval_status: Mapped[str | None] = mapped_column(String(32), default=None)
    advisory_status: Mapped[str | None] = mapped_column(String(32), default=None)

    #: Groups the evaluations produced together, whether by one generation call
    #: or by one bulk re-run. Indexed because ingest and status both read by it.
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[EvaluationTrigger] = mapped_column(
        StrEnumType(EvaluationTrigger, 32), default=EvaluationTrigger.GENERATION
    )

    question: Mapped[QuestionRow] = relationship(back_populates="evaluations")


class JudgeBatchRunRow(TimestampMixin, Base):
    """One bulk judge re-run over the question bank (ADR-030).

    A run is the professor-facing unit; the provider may hold it as several
    jobs, because a bank larger than the per-job cap is split at submission.
    ``provider_batch_ids`` is therefore a list rather than the single id the
    provider returns per job -- polling has to ask about all of them before the
    run itself can be called complete.
    """

    __tablename__ = "judge_batch_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider_batch_ids: Mapped[list[str]] = mapped_column(
        "provider_batch_ids_json", JsonList, default=list, nullable=True
    )

    status: Mapped[JudgeBatchStatus] = mapped_column(
        StrEnumType(JudgeBatchStatus, 32), default=JudgeBatchStatus.SUBMITTED
    )
    model: Mapped[str] = mapped_column(String(200), default="")
    rubric_version: Mapped[str] = mapped_column(String(50), default="")

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    question_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    #: Why a run failed or expired, in the professor's terms. Never a credential.
    error_detail: Mapped[str | None] = mapped_column(Text, default=None)


class ProfessorReviewRow(TimestampMixin, Base):
    """Append-only professor verdict on a question."""

    __tablename__ = "professor_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    decision: Mapped[ReviewDecision] = mapped_column(StrEnumType(ReviewDecision, 16))
    reasons: Mapped[list[RejectionReason]] = mapped_column(
        "reasons_json", EnumList(RejectionReason), default=list, nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    edited_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    edited_reference_solution: Mapped[str | None] = mapped_column(Text, default=None)
    edited_tests: Mapped[str | None] = mapped_column(Text, default=None)
    changed_fields: Mapped[list[str]] = mapped_column(
        "changed_fields_json", JsonList, default=list, nullable=True
    )
    professor_id: Mapped[int | None] = mapped_column(Integer, default=None)
    reviewed_generator_name: Mapped[str | None] = mapped_column(String(200), default=None)
    reviewed_generator_version: Mapped[str | None] = mapped_column(String(50), default=None)

    question: Mapped[QuestionRow] = relationship(back_populates="reviews")


class PreferenceStatementRow(TimestampMixin, Base):
    __tablename__ = "preference_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_text: Mapped[str] = mapped_column(Text)
    category: Mapped[PreferenceCategory] = mapped_column(StrEnumType(PreferenceCategory, 32))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    supporting_review_ids: Mapped[list[int]] = mapped_column(
        "supporting_review_ids_json", JsonList, default=list
    )
    active: Mapped[bool] = mapped_column(default=True)
    confirmation_state: Mapped[PreferenceConfirmationState] = mapped_column(
        StrEnumType(PreferenceConfirmationState, 16), default=PreferenceConfirmationState.INFERRED
    )
    profile_version: Mapped[str] = mapped_column(String(50), default="1")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ReviewEmbeddingRow(TimestampMixin, Base):
    __tablename__ = "review_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("professor_reviews.id", ondelete="CASCADE"), unique=True
    )
    model_id: Mapped[str] = mapped_column(String(200))
    vector: Mapped[list[float]] = mapped_column("vector_json", JsonList)
    content_hash: Mapped[str] = mapped_column(String(64))
