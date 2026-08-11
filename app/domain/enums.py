"""Shared enumerations.

``StrEnum`` is used throughout so values serialise to readable strings in JSON,
templates and SQLite columns without extra conversion code.
"""

from __future__ import annotations

from enum import StrEnum


class BookStatus(StrEnum):
    """Lifecycle of an imported textbook.

    A book document that fails validation is rejected before any row is written,
    so there is no ``FAILED`` state: a book in the database is always one whose
    structure validated. ``PARTIAL`` is a success-with-caveats state, used when
    the document itself declares defects or low-confidence units, so a professor
    is never told a caveated import was clean.
    """

    IMPORTED = "imported"
    PARTIAL = "partial"


class SourceFormat(StrEnum):
    """Accepted upload formats.

    Structured book JSON is the only input the application accepts. Producing that
    JSON from a raw book is out of scope for this application entirely.
    """

    BOOK_JSON = "book_json"


class StructureSource(StrEnum):
    """How a chapter or section boundary was determined.

    Declared *by the book document*, never inferred by this application. It
    records what the producer of the JSON actually relied on, so the professor
    can tell a boundary the source document stated from one a producer guessed at.
    """

    #: The PDF's own outline / bookmarks, i.e. the publisher's table of contents.
    PDF_OUTLINE = "pdf_outline"
    #: Explicit headings in a structured source such as Markdown or HTML.
    MARKDOWN_HEADING = "markdown_heading"
    #: A human authored or corrected this boundary.
    MANUAL = "manual"
    #: The document states the boundary without saying where it came from.
    STRUCTURED_JSON = "structured_json"
    #: The producer had to guess. Trusted least, and flagged in the UI.
    PRODUCER_INFERRED = "producer_inferred"


class StructureConfidence(StrEnum):
    """How much to trust a boundary.

    ``LOW`` means the producer guessed; such units must never be presented as
    though the source document had declared them.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: Confidence implied by each declared source. Keeping the mapping here means a
#: new source value cannot forget to declare how much it should be trusted. A
#: document may also state a unit's confidence explicitly, which wins.
CONFIDENCE_BY_SOURCE: dict[StructureSource, StructureConfidence] = {
    StructureSource.PDF_OUTLINE: StructureConfidence.HIGH,
    StructureSource.MARKDOWN_HEADING: StructureConfidence.HIGH,
    StructureSource.MANUAL: StructureConfidence.HIGH,
    StructureSource.STRUCTURED_JSON: StructureConfidence.HIGH,
    StructureSource.PRODUCER_INFERRED: StructureConfidence.LOW,
}


class WarningSeverity(StrEnum):
    """Whether a warning describes a defect or merely states a fact.

    Only ``DEFECT`` warnings make a book ``PARTIAL``. Without this split, a
    document that simply carries no page numbers would be flagged forever, and a
    badge that is always on teaches the professor to ignore it.
    """

    #: Something was lost, incomplete or guessed at.
    DEFECT = "defect"
    #: True and worth stating, but not a problem with the document.
    INFO = "info"


class ExtractionWarningCode(StrEnum):
    """Machine-readable caveats a book document may declare about itself.

    A closed vocabulary so the UI can group and explain them; ``OTHER`` is the
    escape hatch for a producer-specific caveat, whose detail lives in the
    warning's message.
    """

    #: The source carries no page numbers, so units cite chapter/section only.
    NO_PAGE_NUMBERS = "no_page_numbers"
    #: The producer guessed at one or more boundaries.
    PRODUCER_INFERRED_STRUCTURE = "producer_inferred_structure"
    #: A heading existed in the source but the producer could not read its text.
    MISSING_HEADING = "missing_heading"
    #: Part of the source could not be read and is absent from this document.
    SOURCE_TEXT_UNREADABLE = "source_text_unreadable"
    #: Section text was shortened by the producer.
    SECTION_TEXT_TRUNCATED = "section_text_truncated"
    #: The producer could not determine the title or author.
    METADATA_UNAVAILABLE = "metadata_unavailable"
    #: Anything else; the message must explain it.
    OTHER = "other"


class CurriculumStatus(StrEnum):
    """Lifecycle of a proposed Topic -> Subtopic curriculum.

    Only an ``APPROVED`` curriculum version may ground question generation.
    """

    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class CurriculumItemStatus(StrEnum):
    """A professor's verdict on one proposed topic or subtopic.

    Separate from :class:`CurriculumStatus`, which is the whole version's state:
    a professor works through a proposal item by item, so each item carries its
    own review status. Everything the proposer writes starts at ``PROPOSED``;
    nothing is ever persisted as though it had already been reviewed.
    """

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


class ConceptConfidence(StrEnum):
    """How sure the analysis is about a proposed concept or grouping.

    A coarse three-value band rather than a number: a model asked for "0.83"
    produces a figure with no calibration behind it, whereas high / medium / low
    is a judgement it can actually make and a professor can actually act on.
    Deliberately distinct from :class:`StructureConfidence`, which is about
    *boundaries declared by a book document*, not about instructional analysis.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Difficulty(StrEnum):
    """Question difficulty. Selected from student topic mastery."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class MasteryBand(StrEnum):
    """Coarse band derived from a BKT mastery probability."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class QuestionKind(StrEnum):
    """How a question is scored.

    ``TESTABLE_PROGRAM``: score = passed_tests / total_tests * 100.
    ``DISCRETE``: naturally discrete, scored 0 or 100.
    """

    TESTABLE_PROGRAM = "testable_program"
    DISCRETE = "discrete"


class QuestionType(StrEnum):
    """Assessment format (independent of scoring mode)."""

    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    OUTPUT_PREDICTION = "output_prediction"
    CODE_COMPLETION = "code_completion"
    DEBUGGING = "debugging"
    PARSONS = "parsons"
    CODING = "coding"


class QuestionStatus(StrEnum):
    """Lifecycle of a generated question through validation and review."""

    GENERATED = "generated"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    """A professor's verdict on a generated question.

    ``EDIT`` means approved-with-changes; the generated original is always
    retained alongside the edit (see ``docs/DECISIONS.md``).
    """

    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class RejectionReason(StrEnum):
    """Structured professor rationale for reject or edit decisions."""

    TECHNICALLY_INCORRECT = "technically_incorrect"
    INCORRECT_ANSWER = "incorrect_answer"
    INCORRECT_TESTS = "incorrect_tests"
    NOT_GROUNDED_IN_SOURCE = "not_grounded_in_source"
    WRONG_TOPIC_SUBTOPIC = "wrong_topic_subtopic"
    TOO_EASY = "too_easy"
    TOO_DIFFICULT = "too_difficult"
    AMBIGUOUS = "ambiguous"
    POOR_WORDING = "poor_wording"
    POOR_DISTRACTORS = "poor_distractors"
    POOR_TESTS = "poor_tests"
    NOT_PEDAGOGICALLY_USEFUL = "not_pedagogically_useful"
    TOO_SIMILAR_REPETITIVE = "too_similar_repetitive"
    OTHER = "other"


class GeneratorKind(StrEnum):
    """Which generator produced a question.

    Base and personalized generators must stay distinguishable so their output
    quality can be compared over time.
    """

    BASE = "base"
    PERSONALIZED = "personalized"


class PreferenceCategory(StrEnum):
    WORDING = "wording"
    SCENARIO_STYLE = "scenario_style"
    EMPHASIS = "emphasis"
    DISLIKE = "dislike"
    EXAMPLE_PATTERN = "example_pattern"
    OTHER = "other"


class PreferenceConfirmationState(StrEnum):
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
