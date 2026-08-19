"""ORM tables.

Deliberately minimal: only the tables the professor content pipeline needs to
exist now. This is *not* an attempt to design the final schema. Columns that
belong to deferred features (extracted book structure, generator artefacts,
student progress) are absent on purpose and will be added with the feature that
needs them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.books import ExtractionWarning
from app.domain.enums import (
    BookStatus,
    CalibrationLabel,
    ConceptConfidence,
    CurriculumItemStatus,
    CurriculumStatus,
    Difficulty,
    EvaluationTrigger,
    GeneratorKind,
    JudgeBatchStatus,
    JudgeMetricId,
    QuadrantCell,
    QuestionKind,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
    SourceFormat,
    StructureConfidence,
    StructureSource,
)
from app.domain.mastery import DEFAULT_BKT_PARAMETERS, INITIAL_SUBTOPIC_WEAKNESS
from app.domain.questions import DEFAULT_PRIORITY, GenerationAttempt, QuestionValidationReport
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
    #: Every model call that tried to produce this question (ADR-032). Empty for
    #: rows written before that decision, and for anything the generator got
    #: right first time it holds the single accepted attempt.
    generation_attempts: Mapped[list[GenerationAttempt]] = mapped_column(
        "generation_attempts_json", PydanticList(GenerationAttempt), default=list, nullable=True
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
    #: Eagerly loaded: every reader of a question wants its subtopics, and a
    #: lazy load here is one query per row on the question list and the queue.
    subtopic_links: Mapped[list[QuestionSubtopicRow]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionSubtopicRow.id",
        lazy="selectin",
    )
    #: The subtopic ids as a plain list, readable and assignable like a column,
    #: so callers never have to build join rows by hand.
    subtopic_ids: AssociationProxy[list[int]] = association_proxy(
        "subtopic_links",
        "subtopic_id",
        creator=lambda subtopic_id: QuestionSubtopicRow(subtopic_id=subtopic_id),
    )


class QuestionSubtopicRow(Base):
    """One subtopic a question was tagged with.

    A question belongs to exactly one topic but may exercise several of that
    topic's subtopics, so the tag is a row rather than a column. Weakness is
    tracked per subtopic and a student's score updates every subtopic the
    question touched, which a single column could not express.

    Deleting a subtopic removes its tags and leaves the questions standing: a
    question that outlives one of its tags is still a usable question, and the
    remaining tags are still true.
    """

    __tablename__ = "question_subtopics"
    __table_args__ = (
        UniqueConstraint("question_id", "subtopic_id", name="uq_question_subtopics_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    subtopic_id: Mapped[int] = mapped_column(
        ForeignKey("subtopics.id", ondelete="CASCADE"), index=True
    )

    question: Mapped[QuestionRow] = relationship(back_populates="subtopic_links")


class QuestionEvaluationRow(TimestampMixin, Base):
    """One pedagogical evaluation of a question, retained forever (ADR-030).

    ``questions.pedagogical_eval_json`` holds only the *current* evaluation, so
    re-judging a question used to overwrite what the judge said the first time.
    This table is the append-only history behind that single value: every
    evaluation ever recorded, whichever run produced it.

    The four denormalised columns (``judge_model``, ``rubric_version``,
    ``eval_status``, ``gate``) are plain strings rather than mapped enums
    because their vocabularies belong to :mod:`app.evaluation`, which
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
    #: The derived gate, or ``None`` when too few metrics answered to derive one.
    gate: Mapped[str | None] = mapped_column(String(32), default=None)

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


class QuestionSetVersionRow(TimestampMixin, Base):
    """A frozen list of approved questions, named and dated (ADR-036).

    An adaptive training run must be reproducible: two students following the
    same link have to be answering the same bank, and afterwards it must be
    possible to say what a cohort was actually asked. The question bank itself
    grows continuously, so the unit that a training run points at is a snapshot
    of it, not the bank.

    Nothing here is ever updated. There is no edit path and no repository method
    that writes to an existing row -- a set that could change is not a snapshot,
    and a link into a changing set answers no question about what was served.
    Correcting a set means creating the next one.
    """

    __tablename__ = "question_set_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    #: The taxonomy the members were tagged against. Coverage is meaningless
    #: without it: a count per subtopic needs to know whose subtopics.
    curriculum_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="SET NULL"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    #: How many questions were members at creation, frozen. Compared against the
    #: live member count so a set that lost a row to a deleted question reads as
    #: damaged rather than as a smaller set that was always this size.
    question_count: Mapped[int] = mapped_column(Integer, default=0)

    members: Mapped[list[QuestionSetMemberRow]] = relationship(
        back_populates="set_version",
        cascade="all, delete-orphan",
        order_by="QuestionSetMemberRow.question_id",
    )


class QuestionSetMemberRow(Base):
    """One question's membership of one frozen set.

    Deleting the set deletes its memberships. Deleting a *question* also removes
    its membership, which is why :attr:`QuestionSetVersionRow.question_count`
    records the original size: the loss stays visible instead of rewriting
    history silently.
    """

    __tablename__ = "question_set_members"
    __table_args__ = (
        UniqueConstraint("set_version_id", "question_id", name="uq_question_set_members_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    set_version_id: Mapped[int] = mapped_column(
        ForeignKey("question_set_versions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )

    set_version: Mapped[QuestionSetVersionRow] = relationship(back_populates="members")


class TypeInstructionRow(TimestampMixin, Base):
    """The generation instruction for one question type, learned from reviews.

    Personalization lives here rather than in a block appended to the prompt
    (ADR-033). One row per :class:`~app.domain.enums.QuestionType`, holding the
    text that occupies the type-specific slot the shipped one-liner used to fill.

    ``rules`` is the accumulated list the rewriter edits; ``instruction`` is the
    rendered text actually sent. Keeping both is what lets a rule earned in one
    round survive the next: rewriting the whole instruction from scratch each
    time silently dropped earlier lessons.
    """

    __tablename__ = "type_instructions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_type: Mapped[QuestionType] = mapped_column(
        StrEnumType(QuestionType, 32), unique=True, index=True
    )
    instruction: Mapped[str] = mapped_column(Text)
    #: One entry per learned rule: ``{"rule": str, "review_ids": [int]}``.
    rules: Mapped[list[dict]] = mapped_column("rules_json", JsonList, default=list, nullable=True)
    #: How many reviews the current text was derived from, so a stale instruction
    #: is visible without re-reading every review.
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ReviewOutcomeRow(TimestampMixin, Base):
    """What the judge and the professor said, recorded when the review lands.

    The dataset (ADR-037). One row per review, written at submit time and never
    updated.

    This is deliberately *not* derivable from the live tables. A bulk re-judge
    overwrites ``questions.pedagogical_eval`` (ADR-030), so recomputing the cell
    afterwards would pair yesterday's review with today's judge and silently
    restate history. The row freezes both sides as they stood, together with the
    ``rubric_version`` that produced the gate, which is what makes it usable as
    training or check evidence for a judge repair.

    ``attributed_metrics`` names the individual judges at fault: those that
    passed the question while the professor objected (a ``MISSED`` cell), or
    those that failed it while the professor did not (``FALSE_ALARM``). It is
    empty when no single judge accounts for the disagreement -- an unattributable
    miss is recorded as unattributed rather than blamed on the nearest judge.
    """

    __tablename__ = "review_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Unique: an append-only review gets exactly one outcome. A second row for
    #: the same review would double-count that question in any dataset built here.
    review_id: Mapped[int] = mapped_column(
        ForeignKey("professor_reviews.id", ondelete="CASCADE"), unique=True, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    question_type: Mapped[QuestionType | None] = mapped_column(
        StrEnumType(QuestionType, 32), default=None, index=True
    )

    cell: Mapped[QuadrantCell] = mapped_column(StrEnumType(QuadrantCell, 32), index=True)
    judge: Mapped[CalibrationLabel] = mapped_column(StrEnumType(CalibrationLabel, 16))
    professor: Mapped[CalibrationLabel] = mapped_column(StrEnumType(CalibrationLabel, 16))

    #: The judge version that produced the gate, frozen. Two rows with different
    #: values describe two different judges and must not be pooled into one rate.
    rubric_version: Mapped[str | None] = mapped_column(String(50), default=None)
    judge_model: Mapped[str | None] = mapped_column(String(200), default=None)

    attributed_metrics: Mapped[list[JudgeMetricId]] = mapped_column(
        "attributed_metrics_json", EnumList(JudgeMetricId), default=list, nullable=True
    )
    #: Copied from :func:`app.calibration.is_held_out` at write time so a reader
    #: filtering the dataset states the rule rather than re-deriving it.
    held_out: Mapped[bool] = mapped_column(Boolean, default=False)

    #: What each attributed judge said while getting this question wrong, keyed
    #: by metric. Snapshotted here because it is the evidence a judge repair
    #: reads (ADR-039), and the live evaluation it came from can be overwritten
    #: by a bulk re-judge before anyone gets round to the repair.
    judge_rationales: Mapped[dict] = mapped_column(
        "judge_rationales_json", JsonObject, default=dict, nullable=True
    )

    #: Whether the confirmed-bad cell triggered a type-instruction refresh, and
    #: what happened. A failed refresh is recorded, never silent: the review is
    #: kept either way, so without this the professor could not tell that the
    #: lesson from this review has not reached the generator yet.
    instruction_refreshed: Mapped[bool] = mapped_column(Boolean, default=False)
    refresh_error: Mapped[str | None] = mapped_column(Text, default=None)
    #: The judges relearned because this review disagreed with them (ADR-039).
    judges_refreshed: Mapped[list[JudgeMetricId]] = mapped_column(
        "judges_refreshed_json", EnumList(JudgeMetricId), default=list, nullable=True
    )

    review: Mapped[ProfessorReviewRow] = relationship()
    question: Mapped[QuestionRow] = relationship()


class JudgePromptRow(TimestampMixin, Base):
    """A professor-edited system prompt for one metric judge (ADR-038).

    Absent means the shipped prompt in :mod:`app.evaluation.prompts` is in force.
    A row overrides it.

    ``revision`` counts how often *this* judge was edited. It does not identify
    the judge: the rubric version is a fingerprint of the prompts in force
    (:func:`app.evaluation.judge_prompts.effective_rubric_version`), because a
    counter cannot tell two different prompt sets apart when both have been
    edited the same number of times -- and a reverted judge must not inherit the
    version of the edit it undid.
    """

    __tablename__ = "judge_prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric: Mapped[JudgeMetricId] = mapped_column(
        StrEnumType(JudgeMetricId, 32), unique=True, index=True
    )
    system_prompt: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    #: Why the professor changed it. Not required, but it is the only record of
    #: the reasoning behind a judge that now behaves differently.
    note: Mapped[str | None] = mapped_column(Text, default=None)

    #: Rules learned from disagreements and rendered onto the shipped prompt
    #: (ADR-039), one entry per rule: ``{"rule": str, "question_ids": [int]}``.
    #: Empty for a prompt the professor typed by hand.
    rules: Mapped[list[dict]] = mapped_column("rules_json", JsonList, default=list, nullable=True)
    #: How many disagreements the current rules were learned from, so a stale
    #: judge is visible without re-counting the dataset.
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    #: True when a model wrote this text, false when the professor typed it.
    learned: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class StudentRow(TimestampMixin, Base):
    """A learner the adaptive engine tracks.

    There is no authentication in this application, so a student is a named row
    a professor creates and picks from a list. ``display_name`` is unique because
    that list is the only way to tell two students apart; a cohort containing two
    identical names has to distinguish them, since an ambiguous picker would
    attach one learner's mastery to the other.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)


class StudentTopicMasteryRow(Base):
    """One topic's BKT state for one student.

    Created on first touch with :attr:`BKTParameters.p_init`, never seeded in
    bulk (ADR-041). A topic added to the curriculum after a student began is
    therefore ordinary rather than a special case, and a student who has answered
    nothing owns no rows at all.
    """

    __tablename__ = "student_topic_mastery"
    __table_args__ = (
        UniqueConstraint("student_id", "topic_id", name="uq_student_topic_mastery_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)

    #: P(the student knows this topic). Drives the difficulty band.
    p_known: Mapped[float] = mapped_column(Float, default=DEFAULT_BKT_PARAMETERS.p_init)
    #: How many scores have moved this value, so a confident-looking mastery
    #: built from one answer is distinguishable from one built from twenty.
    observations: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class StudentSubtopicWeaknessRow(Base):
    """One subtopic's weakness for one student -- the roulette weight.

    Created on first touch at :data:`INITIAL_SUBTOPIC_WEAKNESS`, which is the
    maximum, so an untouched subtopic is the most likely to be drawn. It is
    floored rather than allowed to reach zero (ADR-041): a zero weight would
    remove the subtopic from selection permanently.
    """

    __tablename__ = "student_subtopic_weakness"
    __table_args__ = (
        UniqueConstraint("student_id", "subtopic_id", name="uq_student_subtopic_weakness_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    subtopic_id: Mapped[int] = mapped_column(
        ForeignKey("subtopics.id", ondelete="CASCADE"), index=True
    )

    weakness: Mapped[float] = mapped_column(Float, default=INITIAL_SUBTOPIC_WEAKNESS)
    observations: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TrainingSessionRow(TimestampMixin, Base):
    """One student's run against one frozen question set (ADR-036).

    The set is pinned at creation rather than resolved per question, so a run
    stays answerable afterwards: what a student was asked cannot be restated by a
    bank that has grown since.

    ``set_version_id`` is nullable only so that deleting a set leaves the record
    of what students did standing. A session that lost its set reads as damaged
    -- the engine refuses to serve from it -- rather than falling back to the
    live bank, which would be a different experiment wearing the same id.

    ``rng_seed`` makes the roulette reproducible. Each draw uses
    ``Random(f"{rng_seed}:{ordinal}")``, so a run can be replayed exactly without
    storing generator state between requests.
    """

    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    set_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_set_versions.id", ondelete="SET NULL"), default=None, index=True
    )
    rng_seed: Mapped[int] = mapped_column(Integer, default=0)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    student: Mapped[StudentRow] = relationship()
    attempts: Mapped[list[StudentAttemptRow]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="StudentAttemptRow.ordinal",
    )


class StudentAttemptRow(TimestampMixin, Base):
    """One question served to one student, and what happened to it.

    A row is written when the question is *served*, not when it is answered, so
    a question the engine handed out is never lost if the student walks away.
    ``score is None`` is precisely "served, not yet answered".

    ``subtopic_id`` records the subtopic the roulette drew. It is not derivable
    afterwards: a question may carry three subtopics, and which one was being
    exercised is what the draw decided.

    ``requested_difficulty`` and ``served_difficulty`` differ exactly when the
    cell was empty and the engine relaxed difficulty (ADR-041). Storing both is
    what makes an adaptive-looking run auditable -- otherwise a bank with gaps
    reads as a bank that chose those difficulties deliberately.
    """

    __tablename__ = "student_attempts"
    __table_args__ = (
        UniqueConstraint("session_id", "ordinal", name="uq_student_attempts_session_ordinal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True
    )
    #: Denormalized from the session so "everything this student has answered"
    #: is one indexed query rather than a join across every session they own.
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    #: Position within the session, from 1. Also the roulette draw counter.
    ordinal: Mapped[int] = mapped_column(Integer, default=1)

    subtopic_id: Mapped[int | None] = mapped_column(
        ForeignKey("subtopics.id", ondelete="SET NULL"), default=None, index=True
    )
    requested_difficulty: Mapped[Difficulty] = mapped_column(
        StrEnumType(Difficulty, 16), default=Difficulty.EASY
    )
    served_difficulty: Mapped[Difficulty] = mapped_column(
        StrEnumType(Difficulty, 16), default=Difficulty.EASY
    )

    #: The topic's mastery immediately before and after this score, so a progress
    #: page can show movement without replaying every attempt through the model.
    mastery_before: Mapped[float | None] = mapped_column(Float, default=None)
    mastery_after: Mapped[float | None] = mapped_column(Float, default=None)

    #: What the student submitted, verbatim. Text because it is source code for
    #: an executable type and an option index for a discrete one.
    answer: Mapped[str | None] = mapped_column(Text, default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    #: Populated only for executable types, where the score is a test fraction.
    #: Kept beside the score so 60 is distinguishable as 3/5 rather than 6/10.
    passed_tests: Mapped[int | None] = mapped_column(Integer, default=None)
    total_tests: Mapped[int | None] = mapped_column(Integer, default=None)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    session: Mapped[TrainingSessionRow] = relationship(back_populates="attempts")
    question: Mapped[QuestionRow] = relationship()


class UserRow(SQLAlchemyBaseUserTableUUID, Base):
    """The professor console's one identity kind (see ``app/auth/``).

    Fields beyond ``id``/``email``/``hashed_password``/``is_active`` come from
    ``fastapi_users_db_sqlalchemy``. There is no role column: only professors
    log in here, and students never do (ADR-041's join-by-link flow stays
    anonymous).
    """


class AccessTokenRow(SQLAlchemyBaseAccessTokenTableUUID, Base):
    """A live login session (the database auth strategy in ``app/auth/``).

    Deleting a row is what makes logout revoke immediately, unlike a bare JWT
    which would stay valid until it expired.
    """
