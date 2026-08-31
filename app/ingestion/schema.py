"""The structured book document: the shape every import ultimately declares.

This module *is* the ingestion contract. A book document states its own
structure -- chapters, sections, section text, page ranges -- and this module's
job is to validate it and hand back the validated result. It performs no
heading detection, no text segmentation and no guessing of any kind itself.

A JSON upload already has this shape; :func:`parse_book_document` decodes its
transport bytes and validates it. A PDF upload does not, so
:mod:`app.ingestion.pdf` builds this same shape from the PDF's own outline (or,
lacking one, a narrow fallback) and calls :func:`validate_payload` directly --
see ``docs/DECISIONS.md`` ADR-048. Either way, exactly one validation path
decides whether a document is accepted.

Why the contract lives here rather than in a parser
    Heuristic extraction (regular expressions over headings, font-size
    comparisons) is not deterministic across books: rules tuned on one textbook
    silently mis-segment the next, and the failure is invisible because the
    output still looks like a structure. Moving structure to a declared input
    makes ingestion total and reproducible -- the same JSON always yields the
    same rows -- and confines the fallible, book-specific work to one module
    that declares its own uncertainty rather than smoothing it over. See
    ``docs/DECISIONS.md`` ADR-015, ADR-016 and ADR-048.

Validation is strict on purpose
    ``extra="forbid"`` means a misspelled key is an error rather than a silently
    ignored field; a section must carry non-empty text; a chapter must carry at
    least one section; page ranges must not run backwards. A document that fails
    any of these is rejected in full, before anything is written.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.domain.books import BookChapter, BookSection, ExtractionWarning
from app.domain.enums import (
    CONFIDENCE_BY_SOURCE,
    ExtractionWarningCode,
    StructureConfidence,
    StructureSource,
    WarningSeverity,
)
from app.errors import InvalidBookDocumentError

#: The only schema version this application accepts. Bumping it is a breaking
#: change to the contract and needs a new ADR entry.
SCHEMA_VERSION = "1"


class WarningInput(BaseModel):
    """A caveat the document declares about itself."""

    model_config = ConfigDict(extra="forbid")

    code: ExtractionWarningCode
    message: str = Field(min_length=1, max_length=2000)
    location: str | None = Field(default=None, max_length=200)
    severity: WarningSeverity = WarningSeverity.DEFECT

    def to_domain(self) -> ExtractionWarning:
        return ExtractionWarning(
            code=self.code,
            message=self.message,
            location=self.location,
            severity=self.severity,
        )


class _PagedUnit(BaseModel):
    """Shared page-range validation for chapters and sections.

    Whitespace is deliberately *not* stripped model-wide here: section text may
    legitimately begin with indentation (a code listing at the start of a
    section), and trimming it would silently alter the source. Only the label
    fields are normalised, by :meth:`_normalise_labels`.
    """

    model_config = ConfigDict(extra="forbid")

    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)

    @field_validator("number", "title", mode="before", check_fields=False)
    @classmethod
    def _normalise_labels(cls, value: object) -> object:
        """Trim label fields, and treat a blank label as absent.

        A title of ``"   "`` means "no heading here", and must not become a blank
        heading in the professor's view.
        """
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def _check_page_range(self) -> _PagedUnit:
        if (
            self.start_page is not None
            and self.end_page is not None
            and self.end_page < self.start_page
        ):
            raise ValueError(
                f"end_page ({self.end_page}) cannot be before start_page ({self.start_page})"
            )
        return self


class SectionInput(_PagedUnit):
    """One instructional section, as declared by the document.

    ``text`` holds the whole section. There is no size limit and no chunking:
    a long section is one section, because it is one instructional unit.
    """

    #: Section number as printed ("2.1"). ``None`` when the source printed none.
    number: str | None = Field(default=None, max_length=32)
    #: Heading as printed. ``None`` is valid and means "no heading in the source".
    #: It must never be a title the producer made up.
    title: str | None = Field(default=None, max_length=500)
    #: Required and non-empty: a section with no text cannot ground a question,
    #: so a producer must omit it rather than emit an empty shell. The value is
    #: stored verbatim -- see the note on :class:`_PagedUnit` about indentation.
    text: str = Field(min_length=1)
    structure_source: StructureSource = StructureSource.STRUCTURED_JSON
    #: Overrides the confidence implied by ``structure_source`` when the producer
    #: knows better.
    confidence: StructureConfidence | None = None
    warnings: list[WarningInput] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        """Reject whitespace-only text without altering text that has content."""
        if not value.strip():
            raise ValueError("must contain text, not only whitespace")
        return value

    def to_domain(self, *, position: int) -> BookSection:
        return BookSection(
            number=self.number,
            title=self.title,
            position=position,
            text=self.text,
            start_page=self.start_page,
            end_page=self.end_page,
            structure_source=self.structure_source,
            declared_confidence=self.confidence,
            warnings=[warning.to_domain() for warning in self.warnings],
        )


class ChapterInput(_PagedUnit):
    """A chapter, as declared by the document."""

    number: str | None = Field(default=None, max_length=32)
    title: str | None = Field(default=None, max_length=500)
    structure_source: StructureSource = StructureSource.STRUCTURED_JSON
    confidence: StructureConfidence | None = None
    #: At least one section: the section is the unit, so a chapter with none
    #: would contribute no groundable text. A chapter without subdivisions should
    #: declare a single section holding its body.
    sections: list[SectionInput] = Field(min_length=1)

    def to_domain(self, *, position: int, first_section_position: int) -> BookChapter:
        return BookChapter(
            number=self.number,
            title=self.title,
            position=position,
            start_page=self.start_page,
            end_page=self.end_page,
            structure_source=self.structure_source,
            declared_confidence=self.confidence,
            sections=[
                section.to_domain(position=first_section_position + offset)
                for offset, section in enumerate(self.sections)
            ],
        )


class BookDocument(BaseModel):
    """A complete, self-describing textbook ready to be stored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1"]
    #: Whitespace is stripped before the length check, so "   " is rejected rather
    #: than becoming a blank title in the professor's book list.
    title: str = Field(min_length=1, max_length=500)
    #: Only set when the source states it; never guessed from a filename.
    author: str | None = Field(default=None, max_length=500)
    #: What the document was produced from, for provenance only.
    source_filename: str | None = Field(default=None, max_length=500)
    #: Identifies whatever produced this document, and its version, e.g.
    #: "my-converter 1.0" or "hand-authored". Provenance only; never interpreted.
    producer: str | None = Field(default=None, max_length=200)
    page_count: int | None = Field(default=None, ge=0)
    chapters: list[ChapterInput] = Field(min_length=1)
    warnings: list[WarningInput] = Field(default_factory=list)

    @property
    def sections(self) -> list[SectionInput]:
        return [section for chapter in self.chapters for section in chapter.sections]

    @property
    def section_count(self) -> int:
        return len(self.sections)

    def to_domain_chapters(self) -> list[BookChapter]:
        """Convert to domain chapters, numbering sections across the whole book.

        Section positions are book-wide rather than restarted per chapter, so
        ordering by position alone gives true reading order.
        """
        chapters: list[BookChapter] = []
        section_position = 0
        for position, chapter in enumerate(self.chapters):
            chapters.append(
                chapter.to_domain(position=position, first_section_position=section_position)
            )
            section_position += len(chapter.sections)
        return chapters

    def declared_defects(self) -> list[ExtractionWarning]:
        """Document-level warnings that describe an actual problem."""
        return [
            warning.to_domain()
            for warning in self.warnings
            if warning.severity is WarningSeverity.DEFECT
        ]

    def is_partial(self) -> bool:
        """Whether this import must be reported as caveated rather than clean.

        True when the document declares a defect anywhere, or when any unit is
        low-confidence -- that is, the producer guessed at a boundary.
        """
        if self.declared_defects():
            return True
        for chapter in self.chapters:
            units: list[ChapterInput | SectionInput] = [chapter, *chapter.sections]
            for unit in units:
                confidence = unit.confidence or CONFIDENCE_BY_SOURCE[unit.structure_source]
                if confidence is StructureConfidence.LOW:
                    return True
            if any(
                warning.severity is WarningSeverity.DEFECT
                for section in chapter.sections
                for warning in section.warnings
            ):
                return True
        return False


def parse_book_document(data: bytes) -> BookDocument:
    """Parse and validate raw upload bytes as a book document.

    Args:
        data: the uploaded file's bytes, expected to be UTF-8 JSON.

    Returns:
        The validated document.

    Raises:
        InvalidBookDocumentError: if the bytes are not UTF-8, not JSON, not a
            JSON object, or do not satisfy the schema. The error detail names the
            offending fields so the producer can be corrected.
    """
    if not data.strip():
        raise InvalidBookDocumentError("The uploaded file is empty.")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidBookDocumentError(
            "The book document must be UTF-8 encoded JSON.",
            detail=f"Could not decode byte {exc.start} of the file as UTF-8.",
        ) from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidBookDocumentError(
            "The book document is not valid JSON.",
            detail=f"{exc.msg} at line {exc.lineno}, column {exc.colno}.",
        ) from exc

    if not isinstance(payload, dict):
        raise InvalidBookDocumentError(
            "The book document must be a JSON object.",
            detail=f"Found a JSON {type(payload).__name__} at the top level.",
        )

    return validate_payload(payload)


def validate_payload(payload: dict[str, object]) -> BookDocument:
    """Validate a book document already parsed into a plain dict.

    Shared by :func:`parse_book_document` (a JSON upload, once decoded) and
    :mod:`app.ingestion.pdf` (a PDF extraction, which builds this dict directly
    and has no JSON transport bytes to decode). Both producers get the same
    uncompromising schema check.

    Raises:
        InvalidBookDocumentError: the version is missing or unsupported, or the
            payload does not satisfy the schema.
    """
    _require_supported_version(payload)

    try:
        return BookDocument.model_validate(payload)
    except ValidationError as exc:
        raise InvalidBookDocumentError(
            "The book document does not match the expected structure.",
            detail=_describe_validation_error(exc),
        ) from exc


def _require_supported_version(payload: dict[str, object]) -> None:
    """Check the version first, so a mismatch is reported as a version problem.

    Without this, an old document would produce a confusing pile of field errors
    instead of "this is schema version 2, I understand version 1".
    """
    version = payload.get("schema_version")
    if version is None:
        raise InvalidBookDocumentError(
            "The book document does not declare a schema_version.",
            detail=f'Add "schema_version": "{SCHEMA_VERSION}" at the top level.',
        )
    if str(version) != SCHEMA_VERSION:
        raise InvalidBookDocumentError(
            f"Unsupported book document schema version {version!r}.",
            detail=f"This application understands version {SCHEMA_VERSION}.",
        )


def _describe_validation_error(error: ValidationError, limit: int = 8) -> str:
    """Render pydantic's errors as a short, field-by-field explanation."""
    parts: list[str] = []
    for problem in error.errors()[:limit]:
        location = ".".join(str(piece) for piece in problem["loc"]) or "(document root)"
        parts.append(f"{location}: {problem['msg']}")
    remaining = len(error.errors()) - len(parts)
    if remaining > 0:
        parts.append(f"and {remaining} more problem(s)")
    return "; ".join(parts)
