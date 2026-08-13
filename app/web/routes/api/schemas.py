"""Request and response models for the JSON API.

These are the API's contract, deliberately separate from the ORM rows and from
the domain models. A column rename must not silently change the shape a client
depends on, so every response is built by an explicit ``from_row`` constructor
rather than by ``from_attributes`` over a mapped class.

Enum-valued fields serialise as their string value because every enum in
:mod:`app.domain.enums` is a ``StrEnum``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.calibration import (
    CalibrationLabel,
    CalibrationPair,
    CalibrationReport,
    DifficultyConfusion,
    MetricAgreement,
    SubtopicConfusion,
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
from app.domain.feedback import REJECTION_REASON_LABELS
from app.domain.questions import QuestionCheck
from app.evaluation import IngestResult, PedagogicalEvaluation, SubmissionResult
from app.persistence.models import (
    BookRow,
    CurriculumVersionRow,
    JudgeBatchRunRow,
    PreferenceStatementRow,
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    SubtopicEvidenceRow,
    SubtopicRow,
    TopicRow,
)

#: Which generator a generation request should use.
GeneratorChoice = Literal["base", "personalized"]


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
    generators: list[EnumOption]

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
            generators=[
                EnumOption(value="base", label="Base"),
                EnumOption(value="personalized", label="Personalized"),
            ],
        )


class CountsResponse(BaseModel):
    """Dashboard counts, one per section."""

    books: int
    curriculum_versions: int
    questions: int
    reviews: int
    preferences: int
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


class BookListResponse(BaseModel):
    books: list[BookSummary]
    total: int


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

    @classmethod
    def from_row(cls, row: CurriculumVersionRow) -> CurriculumVersionSummary:
        return cls(
            id=row.id,
            label=row.label,
            status=row.status,
            generated_by=row.generated_by,
            source_book_ids=list(row.source_book_ids or []),
            created_at=row.created_at,
            approved_at=row.approved_at,
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
    validation_passed: bool | None
    priority: int
    times_used: int
    is_edited: bool
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
            validation_passed=report.passed if report is not None else None,
            priority=row.priority,
            times_used=row.times_used,
            is_edited=row.original_prompt is not None,
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
    pedagogical_eval: PedagogicalEvaluation | None
    pedagogical_error_message: str | None
    personalization: PersonalizationEvidence | None
    original_prompt: str | None
    original_reference_solution: str | None
    original_tests: str | None
    reviews: list[ReviewOut]


class QuestionListResponse(BaseModel):
    questions: list[QuestionSummary]
    status_counts: dict[str, int]
    total: int


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
    generator: GeneratorChoice = "base"
    seed: str | None = None


class GenerateQuestionsResponse(BaseModel):
    created: int
    question_ids: list[int]
    questions: list[QuestionSummary]


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


# ---------------------------------------------------------------------- preferences


class PreferenceOut(BaseModel):
    """One inferred preference statement and the evidence behind it."""

    id: int
    rule_text: str
    category: PreferenceCategory
    category_label: str
    evidence_count: int
    confidence: float
    supporting_review_ids: list[int]
    active: bool
    confirmation_state: PreferenceConfirmationState
    profile_version: str
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_row(cls, row: PreferenceStatementRow) -> PreferenceOut:
        return cls(
            id=row.id,
            rule_text=row.rule_text,
            category=row.category,
            category_label=row.category.value.replace("_", " "),
            evidence_count=row.evidence_count,
            confidence=row.confidence,
            supporting_review_ids=list(row.supporting_review_ids or []),
            active=row.active,
            confirmation_state=row.confirmation_state,
            profile_version=row.profile_version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class PreferenceListResponse(BaseModel):
    preferences: list[PreferenceOut]
    total: int
    active_count: int


class PreferenceRefreshResponse(BaseModel):
    refreshed: int
    preferences: list[PreferenceOut]


class CorrectPreferenceRequest(BaseModel):
    rule_text: str = Field(min_length=1)


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

    @classmethod
    def from_pair(cls, pair: CalibrationPair) -> CalibrationPairOut:
        return cls(
            question_id=pair.question_id,
            judge=pair.judge,
            professor=pair.professor,
            agrees=pair.agrees,
        )


class CalibrationPairsResponse(BaseModel):
    pairs: list[CalibrationPairOut]
    total: int


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


SubtopicDetail.model_rebuild()
QuestionDetail.model_rebuild()
