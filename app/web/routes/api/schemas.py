"""Request and response models for the JSON API.

These are the API's contract, deliberately separate from the ORM rows and from
the domain models. A column rename must not silently change the shape a client
depends on, so every response is built by an explicit ``from_row`` constructor
rather than by ``from_attributes`` over a mapped class.

Enum-valued fields serialise as their string value because every enum in
:mod:`app.domain.enums` is a ``StrEnum``.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.calibration import (
    MIN_PANEL_SAMPLE,
    AgreementTrend,
    CalibrationLabel,
    CalibrationPair,
    CalibrationReport,
    DifficultyConfusion,
    MetricAgreement,
    QuadrantCell,
    QuadrantCounts,
    SubtopicConfusion,
    TypeCalibration,
)
from app.coverage import CoverageReport, SubtopicCoverage, TopicCoverage
from app.curriculum import (
    DESCRIPTION_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    CurriculumUsage,
    FieldLimit,
)
from app.curriculum.display import DisplayExtractionMetadata, DisplayProposalWarning
from app.domain.books import BookChapter, BookSection, ExtractionWarning, SectionSource
from app.domain.enums import (
    BookStatus,
    ConceptConfidence,
    CurriculumItemStatus,
    CurriculumStatus,
    Difficulty,
    EvaluationTrigger,
    GeneratorKind,
    JudgeBatchStatus,
    JudgeMetricId,
    MasteryBand,
    QuestionKind,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
    SourceFormat,
    StructureConfidence,
    StructureSource,
)
from app.domain.feedback import REJECTION_REASON_LABELS
from app.domain.questions import GenerationAttempt, QuestionCheck
from app.evaluation import IngestResult, PedagogicalEvaluation, SubmissionResult
from app.generation import ChunkQuestionRequest, PlannedQuestion
from app.ingestion import VocabularyTerm
from app.persistence.models import (
    BookRow,
    CurriculumVersionRow,
    JudgeBatchRunRow,
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    QuestionSetVersionRow,
    ReviewOutcomeRow,
    StudentAttemptRow,
    StudentRow,
    SubtopicEvidenceRow,
    SubtopicRow,
    TopicRow,
    TrainingSessionRow,
)
from app.retrieval import RetrievedSection


class EnumOption(BaseModel):
    """One selectable enum value plus the label a UI should show for it."""

    value: str
    label: str


def _options(values: Any, labels: dict[Any, str] | None = None) -> list[EnumOption]:
    return [
        EnumOption(
            value=str(value),
            label=(labels or {}).get(value) or str(value).replace("_", " ").capitalize(),
        )
        for value in values
    ]


# --------------------------------------------------------------------------- system


class HealthResponse(BaseModel):
    """Liveness, including a real database round-trip."""

    status: str
    version: str
    environment: str
    database_ok: bool
    llm_configured: bool
    llm_status: str


class ConfigResponse(BaseModel):
    """Everything a client needs to render forms without hard-coding enums."""

    app_name: str
    version: str
    environment: str
    llm_configured: bool
    llm_status: str
    llm_model: str
    embedding_model: str
    book_schema_version: str
    taxonomy_schema_version: str
    supported_book_extensions: list[str]
    max_book_upload_mb: int
    difficulties: list[EnumOption]
    question_types: list[EnumOption]
    question_statuses: list[EnumOption]
    review_decisions: list[EnumOption]
    rejection_reasons: list[EnumOption]
    #: How many judge calls one generated question costs. A client pricing a
    #: generation run needs this; deriving it from a hard-coded four in the UI
    #: would silently go wrong the day a fifth metric is added (ADR-031).
    judge_calls_per_question: int

    @classmethod
    def build(
        cls,
        *,
        app_name: str,
        version: str,
        environment: str,
        llm_configured: bool,
        llm_status: str,
        llm_model: str,
        embedding_model: str,
        book_schema_version: str,
        taxonomy_schema_version: str,
        supported_book_extensions: tuple[str, ...],
        max_book_upload_mb: int,
    ) -> ConfigResponse:
        return cls(
            app_name=app_name,
            version=version,
            environment=environment,
            llm_configured=llm_configured,
            llm_status=llm_status,
            llm_model=llm_model,
            embedding_model=embedding_model,
            book_schema_version=book_schema_version,
            taxonomy_schema_version=taxonomy_schema_version,
            supported_book_extensions=list(supported_book_extensions),
            max_book_upload_mb=max_book_upload_mb,
            difficulties=_options(Difficulty),
            question_types=_options(QuestionType),
            question_statuses=_options(QuestionStatus),
            review_decisions=_options(ReviewDecision),
            rejection_reasons=_options(RejectionReason, REJECTION_REASON_LABELS),
            judge_calls_per_question=len(JudgeMetricId),
        )


class CountsResponse(BaseModel):
    """Dashboard counts, one per section."""

    books: int
    curriculum_versions: int
    questions: int
    reviews: int
    #: Question types with an instruction learned from reviews (ADR-033).
    learned_instructions: int
    students: int


# --------------------------------------------------------------------------- books


class BookSummary(BaseModel):
    """One book, without its structure."""

    id: int
    title: str
    author: str | None
    status: BookStatus
    source_format: SourceFormat
    original_filename: str
    source_filename: str | None
    producer: str | None
    page_count: int | None
    file_size_bytes: int | None
    notes: str | None
    warning_count: int
    defect_count: int
    created_at: datetime
    imported_at: datetime | None

    @classmethod
    def from_row(cls, row: BookRow) -> BookSummary:
        warnings = row.warnings or []
        return cls(
            id=row.id,
            title=row.title,
            author=row.author,
            status=row.status,
            source_format=row.source_format,
            original_filename=row.original_filename,
            source_filename=row.source_filename,
            producer=row.producer,
            page_count=row.page_count,
            file_size_bytes=row.file_size_bytes,
            notes=row.notes,
            warning_count=len(warnings),
            defect_count=sum(1 for warning in warnings if warning.is_defect),
            created_at=row.created_at,
            imported_at=row.imported_at,
        )


class SectionSummary(BaseModel):
    """One section's identity and location, without its text."""

    id: int
    book_id: int
    chapter_id: int | None
    number: str | None
    title: str | None
    display_title: str
    position: int
    char_count: int
    start_page: int | None
    end_page: int | None
    location_label: str | None
    is_unlabelled: bool
    is_empty: bool
    structure_source: StructureSource
    structure_confidence: StructureConfidence

    @classmethod
    def from_section(cls, section: BookSection) -> SectionSummary:
        return cls(
            id=section.id or 0,
            book_id=section.book_id or 0,
            chapter_id=section.chapter_id,
            number=section.number,
            title=section.title,
            display_title=section.display_title(),
            position=section.position,
            char_count=section.char_count,
            start_page=section.start_page,
            end_page=section.end_page,
            location_label=section.location_label,
            is_unlabelled=section.is_unlabelled,
            is_empty=section.is_empty,
            structure_source=section.structure_source,
            structure_confidence=section.structure_confidence,
        )


class ChapterOut(BaseModel):
    """One chapter and the sections beneath it."""

    id: int
    book_id: int
    number: str | None
    title: str | None
    position: int
    start_page: int | None
    end_page: int | None
    location_label: str | None
    is_unlabelled: bool
    structure_source: StructureSource
    structure_confidence: StructureConfidence
    sections: list[SectionSummary]

    @classmethod
    def from_chapter(cls, chapter: BookChapter) -> ChapterOut:
        return cls(
            id=chapter.id or 0,
            book_id=chapter.book_id or 0,
            number=chapter.number,
            title=chapter.title,
            position=chapter.position,
            start_page=chapter.start_page,
            end_page=chapter.end_page,
            location_label=chapter.location_label,
            is_unlabelled=chapter.is_unlabelled,
            structure_source=chapter.structure_source,
            structure_confidence=chapter.structure_confidence,
            sections=[SectionSummary.from_section(item) for item in chapter.sections],
        )


class BookDetail(BaseModel):
    """One book with its chapter/section hierarchy and import warnings."""

    book: BookSummary
    section_count: int
    chapters: list[ChapterOut]
    warnings: list[ExtractionWarning]
    #: Questions generated from this book's sections. Deleting the book would
    #: strand their grounding citation, so the count is shown before it happens.
    grounded_question_count: int = 0


class BookListResponse(BaseModel):
    books: list[BookSummary]
    total: int


class BookMetadataUpdate(BaseModel):
    """A professor's edit to a book's labels.

    Structure is declared by the imported document and is never edited here, so
    this carries only what the row is labelled with. An omitted field is left
    alone; an empty string clears ``author`` or ``notes``.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)


class BookDeletion(BaseModel):
    """What a completed delete removed, and what it cost."""

    deleted_book_id: int
    #: Questions whose stored grounding now cites sections that no longer exist.
    stranded_question_count: int


class VocabularyTermOut(BaseModel):
    """One closed-vocabulary value, and what it means to a professor."""

    value: str
    meaning: str

    @classmethod
    def from_terms(cls, terms: Iterable[VocabularyTerm]) -> list[VocabularyTermOut]:
        return [cls(value=str(term.value), meaning=term.meaning) for term in terms]


class BookDocumentGuide(BaseModel):
    """Everything a professor needs to obtain a valid book document.

    The prompt and the example are rendered from the ingestion contract itself,
    so a client that shows them cannot describe a document the validator would
    refuse.
    """

    schema_version: str
    supported_extensions: list[str]
    max_upload_mb: int
    #: The copy-and-paste instruction for an assistant. Advisory: it grants
    #: nothing, and the upload is still validated in full.
    prompt: str
    example_json: str
    structure_sources: list[VocabularyTermOut]
    warning_codes: list[VocabularyTermOut]
    warning_severities: list[VocabularyTermOut]


class SectionDetail(BaseModel):
    """One section's full text plus the citation that makes it traceable."""

    section: SectionSummary
    text: str
    warnings: list[ExtractionWarning]
    source: SectionSource
    citation: str


class SectionListResponse(BaseModel):
    sections: list[SectionSummary]
    total: int


# ----------------------------------------------------------------------- curriculum


class SubtopicSummary(BaseModel):
    """One approved subtopic: the unit the adaptive engine tracks weakness for."""

    id: int
    topic_id: int
    stable_id: str | None
    name: str
    description: str | None
    position: int
    review_status: CurriculumItemStatus

    @classmethod
    def from_row(cls, row: SubtopicRow) -> SubtopicSummary:
        return cls(
            id=row.id,
            topic_id=row.topic_id,
            stable_id=row.stable_id,
            name=row.name,
            description=row.description,
            position=row.position,
            review_status=row.review_status,
        )


class TopicOut(BaseModel):
    """One topic: the unit BKT tracks mastery for."""

    id: int
    curriculum_version_id: int
    stable_id: str | None
    name: str
    description: str | None
    position: int
    review_status: CurriculumItemStatus
    subtopics: list[SubtopicSummary]

    @classmethod
    def from_row(cls, row: TopicRow) -> TopicOut:
        return cls(
            id=row.id,
            curriculum_version_id=row.curriculum_version_id,
            stable_id=row.stable_id,
            name=row.name,
            description=row.description,
            position=row.position,
            review_status=row.review_status,
            subtopics=[SubtopicSummary.from_row(item) for item in row.subtopics],
        )


class CurriculumVersionSummary(BaseModel):
    """One curriculum version, without its tree."""

    id: int
    label: str
    status: CurriculumStatus
    generated_by: str | None
    source_book_ids: list[int]
    created_at: datetime
    approved_at: datetime | None
    #: Free: every caller eager-loads topics already.
    topic_count: int
    #: Cannot be derived from the row, so it is a required keyword rather than a
    #: defaulted one -- a default of zero would render a populated version as empty.
    subtopic_count: int

    @classmethod
    def from_row(
        cls, row: CurriculumVersionRow, *, subtopic_count: int
    ) -> CurriculumVersionSummary:
        return cls(
            id=row.id,
            label=row.label,
            status=row.status,
            generated_by=row.generated_by,
            source_book_ids=list(row.source_book_ids or []),
            created_at=row.created_at,
            approved_at=row.approved_at,
            topic_count=len(row.topics),
            subtopic_count=subtopic_count,
        )


class CurriculumVersionDetail(BaseModel):
    """One curriculum version with its Topic -> Subtopic hierarchy."""

    version: CurriculumVersionSummary
    topic_count: int
    subtopic_count: int
    topics: list[TopicOut]
    books: list[BookSummary]
    extraction_metadata: DisplayExtractionMetadata | None
    warnings: list[DisplayProposalWarning]
    #: What deleting this version would strand. On the page that offers the
    #: delete, because the count is only useful before the decision (ADR-045).
    usage: CurriculumVersionUsage


class CurriculumListResponse(BaseModel):
    versions: list[CurriculumVersionSummary]
    approved_version_id: int | None
    latest_version_id: int | None
    total: int


class SubtopicEvidenceOut(BaseModel):
    """Legacy textbook evidence for a subtopic. Taxonomy uploads carry none."""

    id: int
    book_id: int
    section_id: int
    candidate_label: str
    definition: str | None
    citation: str
    quotes: list[str]

    @classmethod
    def from_row(cls, row: SubtopicEvidenceRow) -> SubtopicEvidenceOut:
        return cls(
            id=row.id,
            book_id=row.book_id,
            section_id=row.section_id,
            candidate_label=row.candidate_label,
            definition=row.definition,
            citation=row.citation,
            quotes=list(row.quotes or []),
        )


class SubtopicDetail(BaseModel):
    """One subtopic with its parent topic and any legacy evidence."""

    subtopic: SubtopicSummary
    topic: SubtopicParent
    curriculum_version_id: int
    is_taxonomy_upload: bool
    candidate_labels: list[str]
    grouping_reason: str | None
    confidence: ConceptConfidence | None
    evidence: list[SubtopicEvidenceOut]
    book_count: int


class FieldLimitOut(BaseModel):
    """One field of the taxonomy contract, and the bounds the validator enforces.

    Published structurally as well as inside the prompt, so a form can bind its
    input limits to the contract rather than hard-coding them.
    """

    path: str
    required: bool
    kind: str
    min_length: int | None
    max_length: int | None
    meaning: str

    @classmethod
    def from_limits(cls, limits: Iterable[FieldLimit]) -> list[FieldLimitOut]:
        return [
            cls(
                path=limit.path,
                required=limit.required,
                kind=limit.kind,
                min_length=limit.min_length,
                max_length=limit.max_length,
                meaning=limit.meaning,
            )
            for limit in limits
        ]


class TaxonomyDocumentGuide(BaseModel):
    """Everything a professor needs to obtain a valid taxonomy document.

    The prompt, the example and the field reference are rendered from the
    taxonomy contract itself, so a client that shows them cannot describe a
    document the validator would refuse.
    """

    schema_version: str
    supported_extensions: list[str]
    max_upload_mb: int
    #: The copy-and-paste instruction for an assistant. Advisory: it grants
    #: nothing, and the upload is still validated in full.
    prompt: str
    example_json: str
    fields: list[FieldLimitOut]
    #: A book's uploaded document is retained; a taxonomy's is not, so the
    #: professor's copy is the only copy and a client must not offer a download.
    retains_upload: bool = False


class CurriculumVersionLabelUpdate(BaseModel):
    """A professor's edit to a curriculum version's label.

    The tree is declared by the uploaded document and is never edited here, and
    neither is the version's status: which taxonomy the product is grounded in
    changes by uploading one, not by editing a row (ADR-021).
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(max_length=LABEL_MAX_LENGTH)


class CurriculumItemLabelUpdate(BaseModel):
    """A professor's edit to one topic's or subtopic's display name.

    Only the two label fields exist here, so moving a subtopic between topics,
    reordering, or rewriting a stable id is not refused -- it is inexpressible.
    An omitted field is left alone; an empty description clears it.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)


class CurriculumVersionUsage(BaseModel):
    """What still points at a curriculum version, and how much is unrepairable."""

    question_count: int
    #: Question-to-subtopic taggings. What coverage counts and what the adaptive
    #: engine draws from, so a stranded one silently unservables its question.
    question_subtopic_link_count: int
    #: Frozen sets built against this version (ADR-036). Deleting is refused
    #: outright while this is non-zero -- ``force`` does not apply.
    question_set_count: int
    #: Students whose measured mastery or weakness names its topics or subtopics.
    student_count: int
    attempt_count: int
    #: Whether ``GET /api/curriculum/approved`` currently returns this version.
    is_approved: bool

    @classmethod
    def from_usage(cls, usage: CurriculumUsage) -> CurriculumVersionUsage:
        return cls(
            question_count=usage.question_count,
            question_subtopic_link_count=usage.question_subtopic_link_count,
            question_set_count=usage.question_set_count,
            student_count=usage.student_count,
            attempt_count=usage.attempt_count,
            is_approved=usage.is_approved,
        )


class CurriculumVersionDeletion(BaseModel):
    """What a completed delete removed, and what it cost."""

    deleted_version_id: int
    deleted_topic_count: int
    deleted_subtopic_count: int
    #: The counts as they stood at deletion. Every one of them now names rows
    #: that no longer exist.
    stranded: CurriculumVersionUsage


class SubtopicParent(BaseModel):
    """The topic a subtopic hangs from, without recursing into its siblings."""

    id: int
    name: str
    description: str | None
    stable_id: str | None

    @classmethod
    def from_row(cls, row: TopicRow) -> SubtopicParent:
        return cls(id=row.id, name=row.name, description=row.description, stable_id=row.stable_id)


# ------------------------------------------------------------------------ questions


class InstructionStamp(BaseModel):
    """Which type instruction produced a question (ADR-040).

    ``generator_label`` names the code path and is always ``base@1``; this names
    the text. Two questions with the same label and different fingerprints were
    written from different instructions.
    """

    source: Literal["learned", "shipped"]
    fingerprint: str
    rule_count: int
    review_count: int

    @classmethod
    def from_context(cls, payload: dict[str, Any] | None) -> InstructionStamp | None:
        """Read the stamp, or ``None`` for a question generated before ADR-040.

        Absent is not "shipped": a question written before the stamp existed
        could have used either, and claiming one would be an invention.
        """
        entry = (payload or {}).get("type_instruction")
        if not isinstance(entry, dict):
            return None
        source = entry.get("source")
        if source not in ("learned", "shipped"):
            return None
        return cls(
            source=source,
            fingerprint=str(entry.get("fingerprint", "")),
            rule_count=int(entry.get("rule_count", 0)),
            review_count=int(entry.get("review_count", 0)),
        )


class QuestionSummary(BaseModel):
    """One generated question, without its solution, tests or reports."""

    id: int
    prompt: str
    kind: QuestionKind
    question_type: QuestionType | None
    difficulty: Difficulty
    status: QuestionStatus
    curriculum_version_id: int | None
    topic_id: int | None
    subtopic_ids: list[int]
    generator_kind: GeneratorKind
    generator_name: str
    generator_version: str
    generator_label: str
    #: Which instruction wrote it (ADR-040). ``None`` for a question generated
    #: before the stamp existed.
    instruction: InstructionStamp | None
    validation_passed: bool | None
    priority: int
    times_used: int
    is_edited: bool
    #: The question this one was regenerated from with instructor feedback, or
    #: ``None`` for a directly generated question.
    regenerated_from_question_id: int | None
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_row(cls, row: QuestionRow) -> QuestionSummary:
        report = row.validation_report
        return cls(
            id=row.id,
            prompt=row.prompt,
            kind=row.kind,
            question_type=row.question_type,
            difficulty=row.difficulty,
            status=row.status,
            curriculum_version_id=row.curriculum_version_id,
            topic_id=row.topic_id,
            subtopic_ids=list(row.subtopic_ids),
            generator_kind=row.generator_kind,
            generator_name=row.generator_name,
            generator_version=row.generator_version,
            generator_label=f"{row.generator_name}@{row.generator_version}",
            instruction=InstructionStamp.from_context(row.personalization_context),
            validation_passed=report.passed if report is not None else None,
            priority=row.priority,
            times_used=row.times_used,
            # Whether the professor changed the text, not whether an original was
            # recorded: ``original_prompt`` is seeded on every generated question,
            # so testing it for None reported every question as edited.
            is_edited=row.prompt != row.original_prompt,
            regenerated_from_question_id=row.regenerated_from_question_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class QuestionTaxonomy(BaseModel):
    """Display names for the ids a question carries, resolved where possible."""

    curriculum: str
    topic: str
    #: One entry per claimed subtopic, resolved to a name where possible. A
    #: question can claim several, so this is a list even when it holds one.
    subtopics: list[str]


class PersonalizationEvidence(BaseModel):
    """Which preferences and reviews shaped a personalized question (ADR-025)."""

    preference_ids: list[int]
    review_ids: list[int]
    profile_version: str | None = None


class QuestionDetail(BaseModel):
    """One question with everything the review screen needs."""

    question: QuestionSummary
    reference_solution: str | None
    tests: str | None
    spec: dict[str, Any] | None
    content: dict[str, Any] | None
    sources: list[dict[str, Any]]
    taxonomy: QuestionTaxonomy
    validation_passed: bool | None
    validation_checks: list[QuestionCheck]
    #: Every model call that tried to produce this question, oldest first
    #: (ADR-032). More than one means a classification was refused and retried;
    #: a last entry with ``accepted`` false is why the question failed validation.
    generation_attempts: list[GenerationAttempt]
    pedagogical_eval: PedagogicalEvaluation | None
    pedagogical_error_message: str | None
    personalization: PersonalizationEvidence | None
    original_prompt: str | None
    original_reference_solution: str | None
    original_tests: str | None
    reviews: list[ReviewOut]


class QuestionListResponse(BaseModel):
    questions: list[QuestionSummary]
    #: Always the whole bank, so a filtered listing still reports what it omitted.
    status_counts: dict[str, int]
    #: Whole bank too, keyed by curriculum version id as a string; a question
    #: generated before that column existed is counted under ``"none"``.
    curriculum_version_counts: dict[str, int]
    total: int
    #: The status filter that produced ``questions``, echoed back so a client can
    #: tell a narrowed listing from a bank that happens to hold only these rows.
    status: QuestionStatus | None = None
    curriculum_version_id: int | None = None


#: Which unreviewed questions the review queue offers. ``scoreable`` restricts
#: the pass to questions the judge has already ruled on, because only those can
#: become a calibration pair -- reviewing the rest teaches the professor's
#: preferences but moves no alignment figure.
ReviewQueueMode = Literal["all", "scoreable"]


class ReviewQueueResponse(BaseModel):
    """The next question to review, with enough counts to show progress."""

    mode: ReviewQueueMode
    total: int
    reviewed: int
    remaining: int
    #: Unreviewed questions carrying a completed judge verdict, ignoring the
    #: cursor: the size of the pool this pass can still add to calibration.
    scoreable_remaining: int
    #: ``None`` once the cursor passes the last match. With ``remaining`` above
    #: zero that means questions were skipped, not that the bank is finished.
    question: QuestionDetail | None


class GenerateQuestionsRequest(BaseModel):
    """A generation request.

    Exactly one source selection is required: either ``section_ids`` or
    ``all_sections_of_book``. One question is generated per resolved section.

    No topic or subtopic: the generator reads the section and classifies its own
    question against the approved taxonomy (ADR-031).
    """

    curriculum_version_id: int | None = None
    question_type: QuestionType
    difficulty: Difficulty
    book_id: int | None = None
    section_ids: list[int] | None = None
    all_sections_of_book: bool = False
    seed: str | None = None


class GenerateQuestionsResponse(BaseModel):
    created: int
    question_ids: list[int]
    questions: list[QuestionSummary]


class RegenerateQuestionRequest(BaseModel):
    """Regenerate one existing question with instructor feedback.

    The feedback is threaded into the generation prompt. The source question is
    never modified -- a new question is produced (ADR-002).
    """

    feedback: str = Field(min_length=1, max_length=4000)
    #: Parity with ``ReviewRequest.professor_id``; recorded for provenance only,
    #: not used to switch generators.
    professor_id: int | None = None


class RegenerateQuestionResponse(BaseModel):
    question_id: int
    regenerated_from_question_id: int
    question: QuestionSummary


class ChunkGenerationSpec(BaseModel):
    """One chunk's instruction on the spec sheet (ADR-044).

    ``easy`` / ``medium`` / ``hard`` are how many questions this chunk should
    produce at each difficulty. ``question_types`` is the set they are drawn from,
    not one question per format: two medium questions with three formats chosen is
    still two questions.
    """

    section_id: int
    easy: int = Field(default=0, ge=0, le=20)
    medium: int = Field(default=0, ge=0, le=20)
    hard: int = Field(default=0, ge=0, le=20)
    question_types: list[QuestionType] = Field(default_factory=list)

    def to_request(self) -> ChunkQuestionRequest:
        return ChunkQuestionRequest(
            section_id=self.section_id,
            counts={
                Difficulty.EASY: self.easy,
                Difficulty.MEDIUM: self.medium,
                Difficulty.HARD: self.hard,
            },
            question_types=tuple(self.question_types),
        )


class GenerateBatchRequest(BaseModel):
    """A per-chunk generation run: many chunks, each with its own instruction."""

    curriculum_version_id: int | None = None
    chunks: list[ChunkGenerationSpec] = Field(min_length=1)
    seed: str | None = None


class PlannedQuestionOut(BaseModel):
    """One question a compiled run will ask for, in the order it will be asked."""

    section_id: int
    difficulty: Difficulty
    question_type: QuestionType

    @classmethod
    def from_planned(cls, planned: PlannedQuestion) -> PlannedQuestionOut:
        return cls(
            section_id=planned.section_id,
            difficulty=planned.difficulty,
            question_type=planned.question_type,
        )


class BatchPlanTotals(BaseModel):
    """What a compiled spec sheet costs, before any model call is made."""

    chunks_specified: int
    questions_to_create: int
    generation_calls: int
    #: ``questions_to_create`` times the number of advisory metrics, because the
    #: judge makes one call per metric per question (ADR-031).
    judge_calls: int
    easy: int
    medium: int
    hard: int
    #: Planned questions that repeat a (chunk, difficulty, format) already planned.
    #: Nothing currently makes a repeat differ from the question it repeats, so the
    #: count is reported rather than refused.
    identical_repeats: int


class BatchPlanResponse(BaseModel):
    """The compiled plan for a spec sheet. Read-only: no question is generated."""

    planned: list[PlannedQuestionOut]
    totals: BatchPlanTotals


class GenerateBatchResponse(BaseModel):
    """What a per-chunk run produced, and what it had planned to produce.

    ``created`` may be short of ``planned`` when the provider failed part-way: each
    question commits on its own, so a partial batch is a real outcome (ADR-032).
    """

    created: int
    question_ids: list[int]
    questions: list[QuestionSummary]
    planned: list[PlannedQuestionOut]


class GenerationPlanSection(BaseModel):
    """One candidate source section, and what generating from it would mean."""

    section: SectionSummary
    #: How many questions this section has already produced. Re-generating is
    #: allowed; the count is here so it is a decision rather than an accident.
    existing_question_count: int
    selected: bool
    #: False for a section with no text: the generator would receive nothing, so
    #: the UI disables it rather than letting the run fail one call in.
    selectable: bool


class GenerationPlanChapter(BaseModel):
    """One chapter, and the candidate sections beneath it."""

    id: int
    label: str
    location_label: str | None
    sections: list[GenerationPlanSection]


class GenerationPlanTotals(BaseModel):
    """What the selected run costs, before any model call is made."""

    sections_available: int
    sections_selected: int
    questions_to_create: int
    generation_calls: int
    #: ``sections_selected`` times the number of advisory metrics, because the
    #: judge makes one call per metric per question (ADR-031).
    judge_calls: int
    source_chars: int


class GenerationPlanResponse(BaseModel):
    """The chunk plan: every candidate section, and the cost of the selection."""

    book: BookSummary
    chapters: list[GenerationPlanChapter]
    totals: GenerationPlanTotals
    #: Selected sections that cannot be generated from, named so the professor
    #: can deselect them rather than discovering the problem mid-run.
    blockers: list[str]


# ------------------------------------------------------------------------- feedback


class ReviewRequest(BaseModel):
    """A professor verdict.

    ``prompt`` / ``reference_solution`` / ``tests`` are only read for an ``edit``
    decision; the generated original is never overwritten (ADR-002).
    """

    decision: ReviewDecision
    reasons: list[RejectionReason] = Field(default_factory=list)
    comment: str | None = None
    prompt: str | None = None
    reference_solution: str | None = None
    tests: str | None = None
    professor_id: int | None = None


class ReviewOutcomeOut(BaseModel):
    """What the system did with one review the moment it landed (ADR-037)."""

    cell: QuadrantCell
    judge: CalibrationLabel
    professor: CalibrationLabel
    #: The judges at fault. Empty means no single judge accounts for it.
    attributed_metrics: list[JudgeMetricId]
    attributed_labels: list[str]
    held_out: bool
    #: What the cell calls for, stated rather than left for the client to map.
    action: str
    #: Only the confirmed-bad cell relearns the generator, and only if the model
    #: answered.
    instruction_refreshed: bool = False
    refresh_error: str | None = None
    refresh_rule_count: int | None = None
    #: The judges relearned from this disagreement (ADR-039). Only the two
    #: disagreeing cells ever fill this.
    judges_refreshed: list[JudgeMetricId] = Field(default_factory=list)

    @classmethod
    def from_row(cls, row: ReviewOutcomeRow) -> ReviewOutcomeOut:
        metrics = list(row.attributed_metrics or [])
        return cls(
            cell=row.cell,
            judge=row.judge,
            professor=row.professor,
            attributed_metrics=metrics,
            attributed_labels=[metric.value.replace("_", " ") for metric in metrics],
            held_out=row.held_out,
            action=CELL_ACTIONS[row.cell],
            instruction_refreshed=row.instruction_refreshed,
            refresh_error=row.refresh_error,
            judges_refreshed=list(row.judges_refreshed or []),
        )


#: What each cell calls for, in the professor's terms. One sentence per cell,
#: published in the API so a client states the rule instead of reinventing it.
CELL_ACTIONS: dict[QuadrantCell, str] = {
    QuadrantCell.CONFIRMED_GOOD: (
        "Both accepted. Kept as evidence that would earn auto-acceptance for this type."
    ),
    QuadrantCell.MISSED: (
        "Two things went wrong: the generator wrote a question you would not keep, and the "
        "judge passed it. So this type's instruction relearns and the named judge relearns. "
        "The only cell that makes auto-acceptance unsafe."
    ),
    QuadrantCell.FALSE_ALARM: (
        "The judge flagged a question you approved, so the named judge relearns. This costs "
        "review time, never a student."
    ),
    QuadrantCell.CONFIRMED_BAD: (
        "The judge was right and the question was not good enough. The generator is what "
        "to fix, so this type's instruction is relearned from your reviews."
    ),
}


class ReviewOut(BaseModel):
    """One immutable review record."""

    id: int
    question_id: int
    decision: ReviewDecision
    reasons: list[RejectionReason]
    reason_labels: list[str]
    comment: str | None
    changed_fields: list[str]
    professor_id: int | None
    reviewed_generator_name: str | None
    reviewed_generator_version: str | None
    generator_label: str
    created_at: datetime
    #: Absent when the question carried no completed judge evaluation, so there
    #: was no judge verdict for this review to agree or disagree with.
    outcome: ReviewOutcomeOut | None = None

    @classmethod
    def from_row(cls, row: ProfessorReviewRow) -> ReviewOut:
        reasons = list(row.reasons or [])
        return cls(
            id=row.id,
            question_id=row.question_id,
            decision=row.decision,
            reasons=reasons,
            reason_labels=[REJECTION_REASON_LABELS[reason] for reason in reasons],
            comment=row.comment,
            changed_fields=list(row.changed_fields or []),
            professor_id=row.professor_id,
            reviewed_generator_name=row.reviewed_generator_name,
            reviewed_generator_version=row.reviewed_generator_version,
            generator_label=(
                f"{row.reviewed_generator_name}@{row.reviewed_generator_version}"
                if row.reviewed_generator_name
                else "unknown"
            ),
            created_at=row.created_at,
        )


class ReasonCount(BaseModel):
    code: RejectionReason
    label: str
    count: int


class ReviewStatsResponse(BaseModel):
    reviewed: int
    approved: int
    rejected: int
    edited: int
    reason_distribution: list[ReasonCount]


class ReviewListResponse(BaseModel):
    reviews: list[ReviewOut]
    total: int


# ----------------------------------------------------------------- judge prompts


class MetricFaultsOut(BaseModel):
    """How often one judge was at fault within one panel (ADR-041)."""

    metric: JudgeMetricId
    label: str
    missed: int
    false_alarms: int
    faults: int
    #: Faults per outcome, so panels of different sizes are comparable.
    fault_rate: float | None


class TrendPointOut(BaseModel):
    """One judge panel's agreement record."""

    rubric_version: str | None
    n: int
    first_seen: datetime | None
    last_seen: datetime | None
    confirmed_good: int
    missed: int
    false_alarm: int
    confirmed_bad: int
    agreement: float | None
    auto_accept_precision: float | None
    #: True while ``n`` is too small for the rates to describe the panel rather
    #: than whichever questions happened to be reviewed under it.
    small_sample: bool
    metrics: list[MetricFaultsOut]


class AgreementTrendResponse(BaseModel):
    """Agreement panel by panel, oldest first (ADR-041)."""

    points: list[TrendPointOut]
    total: int
    #: Whether the newest panel agrees more often than the oldest. A direction,
    #: never a significance claim: ``None`` until two panels have been measured.
    improved: bool | None
    min_panel_sample: int

    @classmethod
    def from_trend(cls, trend: AgreementTrend) -> AgreementTrendResponse:
        rates = {point.rubric_version: point.fault_rates for point in trend.points}
        return cls(
            points=[
                TrendPointOut(
                    rubric_version=point.rubric_version,
                    n=point.n,
                    first_seen=point.first_seen,
                    last_seen=point.last_seen,
                    confirmed_good=point.confirmed_good,
                    missed=point.missed,
                    false_alarm=point.false_alarm,
                    confirmed_bad=point.confirmed_bad,
                    agreement=point.agreement,
                    auto_accept_precision=point.auto_accept_precision,
                    small_sample=point.small_sample,
                    metrics=[
                        MetricFaultsOut(
                            metric=row.metric,
                            label=row.metric.value.replace("_", " "),
                            missed=row.missed,
                            false_alarms=row.false_alarms,
                            faults=row.faults,
                            fault_rate=rates[point.rubric_version][row.metric],
                        )
                        for row in point.metrics
                    ],
                )
                for point in trend.points
            ],
            total=trend.total,
            improved=trend.improved,
            min_panel_sample=MIN_PANEL_SAMPLE,
        )


class JudgePromptOut(BaseModel):
    """One metric judge's system prompt, shipped or professor-edited (ADR-038)."""

    metric: JudgeMetricId
    label: str
    #: The text this judge runs now.
    system_prompt: str
    #: The text it would run with no override, so the page can offer a revert
    #: and show what was changed away from.
    shipped_prompt: str
    edited: bool
    #: True when a model wrote the text, false when the professor typed it.
    learned: bool
    #: The rules learned from disagreements and rendered onto the shipped prompt.
    rules: list[str]
    #: How many disagreements the current rules came from.
    evidence_count: int
    #: Disagreements available to learn from now, which is how a stale judge is
    #: visible without re-reading the dataset.
    available_disagreements: int
    #: How often this judge has been rewritten. Informational: the rubric
    #: version, not this counter, is what identifies the panel.
    revision: int
    note: str | None
    updated_at: datetime | None


class JudgePromptListResponse(BaseModel):
    prompts: list[JudgePromptOut]
    #: The name the panel currently answers under. Every evaluation written from
    #: now on carries it, which is what lets calibration separate a repaired
    #: judge from the one it replaced.
    rubric_version: str
    shipped_rubric_version: str


class JudgePromptRequest(BaseModel):
    """A professor's replacement text for one judge."""

    system_prompt: str = Field(min_length=1)
    note: str | None = None

    @field_validator("system_prompt")
    @classmethod
    def _must_say_something(cls, value: str) -> str:
        """Refuse whitespace. A blank prompt would silently disable a judge.

        ``min_length`` alone accepts "   ", which the route then strips to
        nothing -- and a judge asked to answer with no instruction returns
        whatever it likes while still reporting a verdict.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("A judge prompt must not be blank.")
        return stripped


class JudgePromptSaveResponse(BaseModel):
    prompt: JudgePromptOut
    rubric_version: str
    #: True when the save changed the panel's identity, which is the normal case.
    #: False means the submitted text equals what was already in force.
    rubric_version_changed: bool


class JudgePromptRefreshResponse(BaseModel):
    """What one learned judge repair did (ADR-039)."""

    prompt: JudgePromptOut
    rubric_version: str
    rubric_version_changed: bool
    #: False when no attributable disagreement exists yet, so nothing was learned
    #: and the prompt is unchanged.
    learned: bool
    rule_count: int
    evidence_count: int


# ------------------------------------------------------------- type instructions


class TypeInstructionOut(BaseModel):
    """What the generator is told for one question type (ADR-033).

    ``learned`` distinguishes an instruction built from reviews from the shipped
    default, so a professor can see at a glance which types their feedback has
    actually reached. ``available_reviews`` is how many reviews a refresh would
    draw on now, which is what makes a stale instruction visible.
    """

    question_type: QuestionType
    instruction: str
    rules: list[str]
    learned: bool
    review_count: int
    available_reviews: int
    updated_at: datetime | None


class TypeInstructionListResponse(BaseModel):
    instructions: list[TypeInstructionOut]


class TypeInstructionRefreshResponse(BaseModel):
    question_type: QuestionType
    #: False when the type has no reviews yet, leaving the shipped text in place.
    learned: bool
    rule_count: int
    review_count: int
    instruction: str


# ---------------------------------------------------------------------- calibration


class CalibrationResultsResponse(BaseModel):
    """How often the advisory judge agreed with the professor (ADR-029).

    Every rate is ``null`` when its denominator is zero, so a client can tell
    "no data yet" from "agreed with nothing". ``n`` counts questions, not
    reviews, and ``judge_accept_count`` is published so a rate resting on two
    questions is not read as a property of the judge.
    """

    n: int
    judge_accept_count: int
    agreement: float | None
    auto_accept_precision: float | None
    unsafe_auto_accept_rate: float | None
    #: The same pairs split four ways. ``missed`` is the only cell that makes
    #: auto-acceptance unsafe, so it is published beside the rate that hides
    #: it inside a denominator (ADR-034).
    quadrant: QuadrantCounts
    #: Every judge version behind these figures. More than one entry means the
    #: report describes two judges and cannot be read as a property of either.
    rubric_versions: list[str]
    #: Agreement per metric, and the two confusion tables. Present because the
    #: judge and the professor now share one vocabulary, so "how often did the
    #: subtopic reviewer agree" is answerable rather than inferred (ADR-031).
    metrics: list[MetricAgreement]
    subtopic_confusions: list[SubtopicConfusion]
    difficulty_confusions: list[DifficultyConfusion]

    @classmethod
    def from_report(cls, report: CalibrationReport) -> CalibrationResultsResponse:
        return cls(
            n=report.n,
            judge_accept_count=report.judge_accept_count,
            agreement=report.agreement,
            auto_accept_precision=report.auto_accept_precision,
            unsafe_auto_accept_rate=report.unsafe_auto_accept_rate,
            quadrant=report.quadrant,
            rubric_versions=report.rubric_versions,
            metrics=report.metrics,
            subtopic_confusions=report.subtopic_confusions,
            difficulty_confusions=report.difficulty_confusions,
        )


class CalibrationPairOut(BaseModel):
    """One counted question: what the judge said, what the professor said.

    The evidence behind the rates, kept out of ``CalibrationResultsResponse`` so
    that response stays the fixed five-figure summary. Questions excluded from
    the measurement do not appear here at all.
    """

    question_id: int
    judge: CalibrationLabel
    professor: CalibrationLabel
    agrees: bool
    #: Which of the four outcomes this pair is (ADR-034).
    cell: QuadrantCell
    question_type: QuestionType | None
    rubric_version: str | None
    #: Reserved for scoring a repaired judge, so absent from the repair lists
    #: (ADR-035).
    held_out: bool
    #: The judges that passed this question while the professor objected, and
    #: those that failed it while the professor did not. Empty when no single
    #: judge can be held responsible -- which is the honest answer, not a
    #: reason to name the nearest one.
    missed_metrics: list[JudgeMetricId]
    false_alarm_metrics: list[JudgeMetricId]

    @classmethod
    def from_pair(cls, pair: CalibrationPair) -> CalibrationPairOut:
        return cls(
            question_id=pair.question_id,
            judge=pair.judge,
            professor=pair.professor,
            agrees=pair.agrees,
            cell=pair.cell,
            question_type=pair.question_type,
            rubric_version=pair.rubric_version,
            held_out=pair.held_out,
            missed_metrics=pair.missed_metrics,
            false_alarm_metrics=pair.false_alarm_metrics,
        )


class CalibrationPairsResponse(BaseModel):
    pairs: list[CalibrationPairOut]
    total: int


class TypeCalibrationOut(BaseModel):
    """One question type's four-cell report (ADR-034).

    The type is the unit a professor would authorise, because the instruction
    the generator follows is per type (ADR-033). A pooled figure describes a
    mixture of generators and authorises none of them.
    """

    question_type: QuestionType | None
    report: CalibrationResultsResponse
    #: The same arithmetic over held-out pairs only (ADR-035): what a repaired
    #: judge is scored on, as opposed to what a repair is allowed to read.
    check_report: CalibrationResultsResponse
    pairs: list[CalibrationPairOut]

    @classmethod
    def from_type_calibration(cls, calibration: TypeCalibration) -> TypeCalibrationOut:
        return cls(
            question_type=calibration.question_type,
            report=CalibrationResultsResponse.from_report(calibration.report),
            check_report=CalibrationResultsResponse.from_report(calibration.check_report),
            pairs=[CalibrationPairOut.from_pair(pair) for pair in calibration.pairs],
        )


class CalibrationQuadrantResponse(BaseModel):
    """The four-cell breakdown, whole-corpus and per question type."""

    overall: CalibrationResultsResponse
    types: list[TypeCalibrationOut]
    #: Judges whose fault can never be attributed, because the professor's
    #: vocabulary has no reason that contradicts them. Stated rather than
    #: silently omitted.
    unattributable_metrics: list[JudgeMetricId]
    #: One question in this many is held out. Published so a client can state
    #: the rule rather than infer it from which ids happen to be flagged.
    held_out_divisor: int


# ------------------------------------------------------------------ evaluation


class EvaluationHistoryEntry(BaseModel):
    """One retained evaluation of a question (ADR-030).

    ``evaluation`` is the stored blob rather than a parsed
    :class:`PedagogicalEvaluation`, because history includes rows written under
    an older rubric that may no longer validate. Dropping them would be losing
    the record this table exists to keep, so the summary columns beside it are
    what a client should read first.
    """

    id: int
    question_id: int
    run_id: str
    trigger: EvaluationTrigger
    created_at: datetime
    judge_model: str | None
    rubric_version: str | None
    eval_status: str | None
    gate: str | None
    #: How many of the four metrics passed, when the blob is readable. ``None``
    #: for a skipped judgement or one written under a superseded rubric.
    passed_metrics: int | None
    is_current: bool
    evaluation: dict[str, Any] | None

    @classmethod
    def from_row(cls, row: QuestionEvaluationRow, *, is_current: bool) -> EvaluationHistoryEntry:
        metrics = (row.evaluation or {}).get("metrics")
        passed = None
        if isinstance(metrics, list):
            passed = sum(
                1 for metric in metrics if isinstance(metric, dict) and metric.get("passed") is True
            )
        return cls(
            id=row.id,
            question_id=row.question_id,
            run_id=row.run_id,
            trigger=row.trigger,
            created_at=row.created_at,
            judge_model=row.judge_model,
            rubric_version=row.rubric_version,
            eval_status=row.eval_status,
            gate=row.gate,
            passed_metrics=passed,
            is_current=is_current,
            evaluation=row.evaluation,
        )


class EvaluationHistoryResponse(BaseModel):
    """A question's judge history, newest first."""

    question_id: int
    evaluations: list[EvaluationHistoryEntry]
    total: int


class JudgeBatchRunOut(BaseModel):
    """One bulk re-run, as a professor needs to see it.

    ``provider_batch_ids`` is a list because a bank larger than the per-job cap
    is split into several provider jobs that share this one run id.
    """

    run_id: str
    status: JudgeBatchStatus
    model: str
    rubric_version: str
    provider_batch_ids: list[str]
    question_count: int
    completed_count: int
    failed_count: int
    submitted_at: datetime | None
    completed_at: datetime | None
    error_detail: str | None

    @classmethod
    def from_row(cls, row: JudgeBatchRunRow) -> JudgeBatchRunOut:
        return cls(
            run_id=row.run_id,
            status=row.status,
            model=row.model,
            rubric_version=row.rubric_version,
            provider_batch_ids=list(row.provider_batch_ids or []),
            question_count=row.question_count,
            completed_count=row.completed_count,
            failed_count=row.failed_count,
            submitted_at=row.submitted_at,
            completed_at=row.completed_at,
            error_detail=row.error_detail,
        )


class SubmitBatchRunRequest(BaseModel):
    """Optional narrowing of a re-run to named questions.

    Omitted means the whole eligible bank. Ineligible ids are dropped rather
    than rejected: the eligibility rule is ADR-024's, not the caller's to waive.
    """

    question_ids: list[int] | None = None


class SubmitBatchRunResponse(BaseModel):
    """What a submission did, including the one-off backfill it may have run."""

    run: JudgeBatchRunOut
    submitted: int
    skipped: int
    backfilled: int

    @classmethod
    def from_result(cls, result: SubmissionResult) -> SubmitBatchRunResponse:
        return cls(
            run=JudgeBatchRunOut.from_row(result.run),
            submitted=result.submitted,
            skipped=result.skipped,
            backfilled=result.backfilled,
        )


class BatchRunListResponse(BaseModel):
    runs: list[JudgeBatchRunOut]
    total: int


class PollBatchRunResponse(BaseModel):
    """What one poll collected.

    ``already_recorded`` is published so that re-polling a finished run reads as
    "nothing new" rather than as a run that produced nothing.
    """

    run: JudgeBatchRunOut
    status: JudgeBatchStatus
    ingested: int
    failed: int
    already_recorded: int

    @classmethod
    def from_result(cls, result: IngestResult) -> PollBatchRunResponse:
        return cls(
            run=JudgeBatchRunOut.from_row(result.run),
            status=result.status,
            ingested=result.ingested,
            failed=result.failed,
            already_recorded=result.already_recorded,
        )


# -------------------------------------------------------------------- coverage


class CoverageReportResponse(BaseModel):
    """The subtopic x difficulty grid, and what it means (ADR-036).

    ``empty_cells`` and ``thin_cells`` stay separate: an empty cell is a request
    the adaptive engine cannot satisfy, a thin one is satisfied repetitively.
    ``is_servable`` is the blocking condition; ``is_ready`` is the comfortable
    one.
    """

    curriculum_version_id: int | None
    curriculum_label: str | None
    set_version_id: int | None
    minimum_per_cell: int
    question_count: int
    total_cells: int
    empty_cells: int
    thin_cells: int
    ready_cells: int
    #: Cells still owed questions, empty and thin alike. The unit the page
    #: counts in, because one question can close a gap in three rows at once.
    gap_count: int
    #: Sum of the per-cell shortfalls. An upper bound on the questions to write.
    questions_needed: int
    is_servable: bool
    is_ready: bool
    #: The rows grouped as the professor reads them, in taxonomy order.
    topics: list[TopicCoverage]
    #: The same rows, flat. Kept because a client asking "which subtopics are
    #: short" should not have to walk a tree to find out.
    subtopics: list[SubtopicCoverage]

    @classmethod
    def from_report(cls, report: CoverageReport) -> CoverageReportResponse:
        return cls(
            curriculum_version_id=report.curriculum_version_id,
            curriculum_label=report.curriculum_label,
            set_version_id=report.set_version_id,
            minimum_per_cell=report.minimum_per_cell,
            question_count=report.question_count,
            total_cells=report.total_cells,
            empty_cells=report.empty_cells,
            thin_cells=report.thin_cells,
            ready_cells=report.ready_cells,
            gap_count=report.gap_count,
            questions_needed=report.questions_needed,
            is_servable=report.is_servable,
            is_ready=report.is_ready,
            topics=report.topics,
            subtopics=report.subtopics,
        )


class CoverageTargetRef(BaseModel):
    """One cell a professor asked to have filled."""

    subtopic_id: int
    difficulty: Difficulty


class FillGapsRequest(BaseModel):
    """The gaps a professor selected on the coverage page.

    Deliberately a list of *targets*, not a question count. The generator picks
    its own topic and subtopics from the chunk it is given (ADR-031), so asking
    for "seven questions" would promise an aim the generator does not accept.
    """

    targets: list[CoverageTargetRef] = Field(min_length=1)


class GeneratedRunQuestion(BaseModel):
    """One question a generation run produced, and how its aim landed.

    ``requested_subtopic_id`` is the gap the professor picked; ``claimed_*`` is
    what the generator classified the question as after reading the section
    (ADR-031). ``aim_matched`` is the two agreeing at the topic level -- reported,
    never used to filter, so a drift is visible in the review queue instead.
    """

    question_id: int
    requested_subtopic_id: int
    requested_difficulty: Difficulty
    claimed_topic_id: int | None
    claimed_subtopic_ids: list[int]
    section_id: int
    status: QuestionStatus
    aim_matched: bool


class SkippedRunTarget(BaseModel):
    """A gap target the run did not generate for, and why."""

    subtopic_id: int
    difficulty: Difficulty
    reason: str


class FailedRunTarget(BaseModel):
    """A gap target whose generation call reached the provider and failed.

    The section was retrieved and the request was well formed; the model call
    itself did not return a usable question. What the run already produced is
    kept (ADR-032), so this is reported beside ``generated`` rather than raised.
    """

    subtopic_id: int
    difficulty: Difficulty
    section_id: int
    error: str


class GenerationRunResponse(BaseModel):
    """The outcome of one coverage "Generate" run.

    Always 200, even when ``failed`` is non-empty: a run that produced some
    questions and lost others part-way is a real, reportable outcome, not an
    error to swallow the successes for.
    """

    run_id: str
    generated: list[GeneratedRunQuestion]
    skipped: list[SkippedRunTarget]
    failed: list[FailedRunTarget]


class QuestionSetOut(BaseModel):
    """One frozen set of approved questions.

    ``question_count`` is what was frozen; ``member_count`` is what is still
    there. They differ only if a member question was deleted, and publishing
    both is what makes that visible rather than silently rewriting the set's
    size.
    """

    id: int
    label: str
    notes: str | None
    curriculum_version_id: int | None
    question_count: int
    member_count: int
    created_at: datetime
    question_ids: list[int]
    is_prod: bool = False

    @classmethod
    def from_row(cls, row: QuestionSetVersionRow, *, is_prod: bool = False) -> QuestionSetOut:
        return cls(
            id=row.id,
            label=row.label,
            notes=row.notes,
            curriculum_version_id=row.curriculum_version_id,
            question_count=row.question_count,
            member_count=len(row.members),
            created_at=row.created_at,
            question_ids=[member.question_id for member in row.members],
            is_prod=is_prod,
        )


class QuestionSetListResponse(BaseModel):
    sets: list[QuestionSetOut]
    total: int


class CreateQuestionSetRequest(BaseModel):
    """Freeze the currently approved questions under a name."""

    label: str = Field(min_length=1, max_length=200)
    notes: str | None = None


# -------------------------------------------------------------------- students


class StudentOut(BaseModel):
    """One learner. No credentials: there is no authentication (ADR-041)."""

    id: int
    display_name: str
    email: str
    created_at: datetime
    answered_count: int = 0

    @classmethod
    def from_row(cls, row: StudentRow, *, answered_count: int = 0) -> StudentOut:
        return cls(
            id=row.id,
            display_name=row.display_name,
            email=row.email,
            created_at=row.created_at,
            answered_count=answered_count,
        )


class StudentRosterRowOut(BaseModel):
    """One learner as the roster table shows them.

    Carries the attempt aggregates the roster used to derive on the client from
    a per-student progress fetch: the average, the answered count, when they were
    last active, and the running-average series the row sparkline draws.
    """

    id: int
    display_name: str
    email: str
    created_at: datetime
    answered_count: int = 0
    average_score: float | None = None
    last_activity_at: datetime | None = None
    score_series: list[float] = Field(default_factory=list)


class StudentListResponse(BaseModel):
    """A page of the roster. ``total`` counts the learners matching the filters,
    not the page, so the client can render page controls."""

    students: list[StudentRosterRowOut]
    total: int
    page: int = 1
    page_size: int = 20


class ClassTrendAttemptOut(BaseModel):
    """One scored answer, cohort-wide, for the class trend graph."""

    student_id: int
    score: float
    answered_at: datetime | None = None
    created_at: datetime
    ordinal: int


class ClassWeaknessStudentOut(BaseModel):
    id: int
    name: str
    weakness: float
    answered: int


class ClassWeaknessCellOut(BaseModel):
    subtopic_id: int
    subtopic_name: str
    topic_name: str
    average_weakness: float
    student_count: int
    affected: list[ClassWeaknessStudentOut] = Field(default_factory=list)


class ClassSummaryOut(BaseModel):
    """Cohort-wide numbers the roster's aggregate cards need, computed over every
    learner regardless of which roster page is open."""

    student_count: int
    measured_students: int
    average_score: float | None = None
    scored_attempts: list[ClassTrendAttemptOut] = Field(default_factory=list)
    weakness_cells: list[ClassWeaknessCellOut] = Field(default_factory=list)


class StudentIdentityOut(BaseModel):
    """A learner plus the token their browser keeps to come back as them.

    Returned only from enrolment and resume -- the two calls a student's own
    browser makes. The professor-facing :class:`StudentOut` never carries the
    token.
    """

    id: int
    display_name: str
    email: str
    created_at: datetime
    resume_token: str

    @classmethod
    def from_row(cls, row: StudentRow) -> StudentIdentityOut:
        return cls(
            id=row.id,
            display_name=row.display_name,
            email=row.email,
            created_at=row.created_at,
            resume_token=row.resume_token,
        )


class CreateStudentRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class ResumeStudentRequest(BaseModel):
    """A returning browser identifying itself against one classroom link."""

    resume_token: str = Field(min_length=1, max_length=64)
    set_version_id: int


class TrainingSessionOut(BaseModel):
    """One run against one frozen question set (ADR-036)."""

    id: int
    student_id: int
    student_name: str | None
    set_version_id: int | None
    set_label: str | None
    rng_seed: int
    created_at: datetime
    ended_at: datetime | None
    served_count: int
    answered_count: int

    @classmethod
    def from_row(
        cls,
        row: TrainingSessionRow,
        *,
        student_name: str | None = None,
        set_label: str | None = None,
    ) -> TrainingSessionOut:
        attempts = list(row.attempts)
        return cls(
            id=row.id,
            student_id=row.student_id,
            student_name=student_name,
            set_version_id=row.set_version_id,
            set_label=set_label,
            rng_seed=row.rng_seed,
            created_at=row.created_at,
            ended_at=row.ended_at,
            served_count=len(attempts),
            answered_count=sum(1 for attempt in attempts if attempt.score is not None),
        )


class StudentResumeOut(BaseModel):
    """Who a resume token belongs to, and the run to drop them back into if any."""

    student: StudentIdentityOut
    active_session: TrainingSessionOut | None


class TrainingSessionListResponse(BaseModel):
    sessions: list[TrainingSessionOut]
    total: int


class StartTrainingSessionRequest(BaseModel):
    student_id: int
    set_version_id: int


class ParsonsBlockOut(BaseModel):
    """One draggable block, including the indentation it should display with."""

    id: str
    text: str
    indent: int = Field(ge=0)


class ServedQuestionOut(BaseModel):
    """One question as the student sees it.

    Every presentable field is listed explicitly. The stored ``content`` is never
    published as-is, because it holds the answer -- ``correct_option_index``,
    ``correct_answer``, ``expected_output``, ``correct_order`` and
    ``reference_solution`` all live there. A whitelist per type is the only shape
    where adding a question format cannot leak its answer by default.
    """

    training_session_id: int
    attempt_id: int
    ordinal: int
    #: True when this was already outstanding rather than freshly drawn.
    resumed: bool
    #: True when the requested difficulty was unavailable (ADR-041).
    fallback_used: bool
    requested_difficulty: Difficulty
    served_difficulty: Difficulty
    subtopic_id: int | None
    subtopic_name: str | None
    question_id: int
    question_type: QuestionType | None
    prompt: str
    #: Multiple choice only.
    options: list[str] | None = None
    #: Output prediction, code completion and debugging: the code to reason about.
    code: str | None = None
    #: Parsons only, in a shuffled order the student has to fix.
    blocks: list[ParsonsBlockOut] | None = None

    @classmethod
    def from_served(cls, served: Any, *, subtopic_name: str | None = None) -> ServedQuestionOut:
        attempt = served.attempt
        question = served.question
        content = question.content or {}
        return cls(
            training_session_id=attempt.session_id,
            attempt_id=attempt.id,
            ordinal=attempt.ordinal,
            resumed=served.resumed,
            fallback_used=served.fallback_used,
            requested_difficulty=attempt.requested_difficulty,
            served_difficulty=attempt.served_difficulty,
            subtopic_id=attempt.subtopic_id,
            subtopic_name=subtopic_name,
            question_id=question.id,
            question_type=question.question_type,
            prompt=question.prompt,
            options=_presentable_options(question.question_type, content),
            code=_presentable_code(question.question_type, content),
            blocks=_presentable_blocks(question.question_type, content, seed=attempt.id),
        )


def _presentable_options(question_type: QuestionType | None, content: dict) -> list[str] | None:
    if question_type is not QuestionType.MULTIPLE_CHOICE:
        return None
    options = content.get("options")
    if not isinstance(options, list):
        return None
    return [str(option) for option in options]


def _presentable_code(question_type: QuestionType | None, content: dict) -> str | None:
    """The code a student reads or edits -- never the reference solution."""
    if question_type not in {
        QuestionType.OUTPUT_PREDICTION,
        QuestionType.CODE_COMPLETION,
        QuestionType.DEBUGGING,
    }:
        return None
    code = content.get("code")
    return code if isinstance(code, str) else None


def _presentable_blocks(
    question_type: QuestionType | None, content: dict, *, seed: int
) -> list[ParsonsBlockOut] | None:
    """Parsons blocks, shuffled.

    Stored order is the correct order, so publishing it unshuffled would answer
    the puzzle. The shuffle is seeded on the attempt id so a reload shows the
    same arrangement rather than silently re-posing the question.
    """
    if question_type is not QuestionType.PARSONS:
        return None
    blocks = content.get("blocks")
    if not isinstance(blocks, list):
        return None
    presentable = [
        ParsonsBlockOut(
            id=str(block.get("id")),
            text=str(block.get("text")),
            indent=block.get("indent", 0) if isinstance(block.get("indent", 0), int) else 0,
        )
        for block in blocks
        if isinstance(block, dict) and block.get("id") is not None and block.get("text") is not None
    ]
    random.Random(seed).shuffle(presentable)
    return presentable


class AnswerRequest(BaseModel):
    answer: str = ""


class AnsweredOut(BaseModel):
    """What one submitted answer was worth, and what it moved."""

    training_session_id: int
    attempt_id: int
    question_id: int
    score: float
    passed_tests: int | None
    total_tests: int | None
    #: Failing-test evidence, or the author's explanation for a discrete question.
    detail: str | None
    mastery_before: float | None
    mastery_after: float | None

    @classmethod
    def from_result(cls, result: Any) -> AnsweredOut:
        attempt = result.attempt
        return cls(
            training_session_id=attempt.session_id,
            attempt_id=attempt.id,
            question_id=attempt.question_id,
            score=result.scored.score,
            passed_tests=result.scored.passed_tests,
            total_tests=result.scored.total_tests,
            detail=result.scored.detail,
            mastery_before=result.mastery_before,
            mastery_after=result.mastery_after,
        )


class TopicMasteryOut(BaseModel):
    """One topic's BKT state, and the difficulty it currently implies."""

    topic_id: int
    topic_name: str
    p_known: float
    band: MasteryBand
    next_difficulty: Difficulty
    observations: int


class SubtopicWeaknessOut(BaseModel):
    """One subtopic's weakness -- its weight in the roulette."""

    subtopic_id: int
    subtopic_name: str
    topic_name: str
    weakness: float
    observations: int


class AttemptOut(BaseModel):
    """One question served to a student, answered or not."""

    id: int
    session_id: int
    ordinal: int
    question_id: int
    question_type: QuestionType | None
    subtopic_id: int | None
    requested_difficulty: Difficulty
    served_difficulty: Difficulty
    score: float | None
    passed_tests: int | None
    total_tests: int | None
    #: What the student submitted, verbatim -- an option index for a discrete
    #: type, source code for an executable one. ``None`` while the attempt is
    #: still open. Lets a past-question review show the learner's own choice
    #: beside the correct answer.
    answer: str | None
    created_at: datetime
    answered_at: datetime | None

    @classmethod
    def from_row(cls, row: StudentAttemptRow) -> AttemptOut:
        return cls(
            id=row.id,
            session_id=row.session_id,
            ordinal=row.ordinal,
            question_id=row.question_id,
            question_type=row.question.question_type if row.question else None,
            subtopic_id=row.subtopic_id,
            requested_difficulty=row.requested_difficulty,
            served_difficulty=row.served_difficulty,
            score=row.score,
            passed_tests=row.passed_tests,
            total_tests=row.total_tests,
            answer=row.answer,
            created_at=row.created_at,
            answered_at=row.answered_at,
        )


class StudentProgressOut(BaseModel):
    """Everything measured about one learner.

    ``topics`` and ``subtopics`` list only what has actually been scored. State
    rows are created on first touch (ADR-041), so an untouched subtopic has no
    row and appears here as nothing rather than as a fabricated starting value.
    """

    student: StudentOut
    answered: int
    average_score: float | None
    topics: list[TopicMasteryOut]
    subtopics: list[SubtopicWeaknessOut]
    recent_attempts: list[AttemptOut]
    sessions: list[TrainingSessionOut]


class RetrievedSectionOut(BaseModel):
    """One book section returned by semantic retrieval, with its citation."""

    section_id: int
    book_id: int
    book_title: str
    chapter_title: str | None
    section_number: str | None
    section_title: str | None
    score: float
    snippet: str

    @classmethod
    def from_result(cls, result: RetrievedSection) -> RetrievedSectionOut:
        return cls(
            section_id=result.section_id,
            book_id=result.book_id,
            book_title=result.book_title,
            chapter_title=result.chapter_title,
            section_number=result.section_number,
            section_title=result.section_title,
            score=result.score,
            snippet=result.snippet,
        )


SubtopicDetail.model_rebuild()
QuestionDetail.model_rebuild()
