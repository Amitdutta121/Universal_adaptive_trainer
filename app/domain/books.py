"""Source book entities: the imported textbook and its declared structure.

The instructional **section** is the primary unit of this model. A section is a
semantic textbook section, not a fixed-size chunk: later systems may split a long
section internally for model-context reasons, but what is stored, shown to the
professor and cited by generation is the section itself.

Structure is **declared by the book document**, never inferred here -- see
:mod:`app.ingestion.schema` and ``docs/DECISIONS.md`` ADR-015. Two honesty rules
are still encoded in these types rather than left to convention:

1. A section title is ``None`` when the source had no heading there. Titles are
   never invented -- see :meth:`BookSection.display_title`, which falls back to
   the printed number and then to a *location* description ("Pages 12-13"),
   never to a made-up heading.
2. Every chapter and section records where its boundary came from
   (:class:`~app.domain.enums.StructureSource`) and how much that is worth
   trusting (:class:`~app.domain.enums.StructureConfidence`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.domain.enums import (
    CONFIDENCE_BY_SOURCE,
    BookStatus,
    ExtractionWarningCode,
    SourceFormat,
    StructureConfidence,
    StructureSource,
    WarningSeverity,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _page_range_label(start_page: int | None, end_page: int | None) -> str | None:
    """Describe a page range for display. Returns ``None`` when unknown."""
    if start_page is None:
        return None
    if end_page is None or end_page == start_page:
        return f"Page {start_page}"
    return f"Pages {start_page}\u2013{end_page}"


class ExtractionWarning(BaseModel):
    """One thing that went wrong, or could not be determined, during extraction.

    Warnings are surfaced to the professor rather than logged and forgotten: an
    extraction that quietly dropped half a book is worse than one that says so.
    """

    model_config = ConfigDict(frozen=True)

    code: ExtractionWarningCode
    message: str = Field(min_length=1)
    #: Where the problem occurred, e.g. "page 42" or "section 3.1". Optional
    #: because some warnings are document-wide.
    location: str | None = None
    #: Defaults to ``DEFECT``: a new warning is treated as a problem until it is
    #: explicitly declared informational, so the failure mode is over-reporting
    #: rather than hiding something.
    severity: WarningSeverity = WarningSeverity.DEFECT

    @property
    def is_defect(self) -> bool:
        return self.severity is WarningSeverity.DEFECT

    def __str__(self) -> str:
        return f"{self.message} ({self.location})" if self.location else self.message


class SectionSource(BaseModel):
    """Everything needed to cite a section back to the book it came from.

    This is the traceability contract that later question generation depends on:
    given a section, a generated question can name the book, chapter, section and
    pages it was grounded in.
    """

    model_config = ConfigDict(from_attributes=True)

    book_id: int
    book_title: str
    book_author: str | None = None
    section_id: int
    chapter_id: int | None = None
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    section_title: str | None = None
    start_page: int | None = None
    end_page: int | None = None
    structure_source: StructureSource
    structure_confidence: StructureConfidence

    @computed_field  # type: ignore[prop-decorator]
    @property
    def location_label(self) -> str | None:
        """Human-readable page location, or ``None`` if pages are unknown."""
        return _page_range_label(self.start_page, self.end_page)

    @property
    def chapter_label(self) -> str | None:
        """The chapter as printed, or reconstructed from its number.

        A chapter whose heading was only "Chapter 3" has a number and no title;
        rebuilding "Chapter 3" from the number is not a fabrication, whereas
        inventing a descriptive title would be.
        """
        if self.chapter_title:
            return " ".join(p for p in (self.chapter_number, self.chapter_title) if p)
        if self.chapter_number:
            return f"Chapter {self.chapter_number}"
        return None

    @property
    def section_label(self) -> str | None:
        """The section as printed, or ``None`` when it had no heading at all."""
        if self.section_title:
            return " ".join(p for p in (self.section_number, self.section_title) if p)
        return self.section_number or None

    def citation(self) -> str:
        """A single-line citation, e.g. ``Think Python, Chapter 2, 2.1 Values (Page 15)``.

        Degrades gracefully: a section with no heading cites the book and page
        alone rather than claiming a title it does not have.
        """
        parts = [self.book_title, self.chapter_label, self.section_label]
        citation = ", ".join(part for part in parts if part)
        location = self.location_label
        return f"{citation} ({location})" if location else citation


class BookSection(BaseModel):
    """One instructional section of a textbook."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    book_id: int | None = None
    chapter_id: int | None = None

    #: Section number as printed ("2.1"). ``None`` when the document had none.
    number: str | None = None
    #: Heading text as printed. ``None`` when no heading was found -- never invented.
    title: str | None = None
    position: int = Field(default=0, ge=0)

    text: str = ""
    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)

    structure_source: StructureSource
    #: Set when the book document states a confidence explicitly, overriding the
    #: one implied by ``structure_source``.
    declared_confidence: StructureConfidence | None = None
    warnings: list[ExtractionWarning] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def structure_confidence(self) -> StructureConfidence:
        return self.declared_confidence or CONFIDENCE_BY_SOURCE[self.structure_source]

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    @property
    def has_detected_heading(self) -> bool:
        """True when a heading *title* was found in the document."""
        return self.title is not None

    @property
    def is_unlabelled(self) -> bool:
        """True when the document gave neither a title nor a number.

        This -- not :attr:`has_detected_heading` -- is what the UI should warn
        about. A unit printed as "4" with no title still came from a real
        boundary; only a unit with nothing at all is identified purely by
        location.
        """
        return self.title is None and not self.number

    @property
    def location_label(self) -> str | None:
        return _page_range_label(self.start_page, self.end_page)

    def display_title(self) -> str:
        """A label safe to show in the UI.

        Falls back to the printed number, then the page location, then the
        position -- never to an invented heading. A number the document itself
        prints is not a fabrication, so "Section 4" is preferred over calling a
        numbered unit untitled. Callers that need to know whether a real heading
        was found should check :attr:`has_detected_heading`.
        """
        if self.title:
            return " ".join(p for p in (self.number, self.title) if p)
        if self.number:
            return f"Section {self.number}"
        location = self.location_label
        if location:
            return f"Untitled section ({location})"
        return f"Untitled section {self.position + 1}"


class BookChapter(BaseModel):
    """A chapter grouping sections. May itself be inferred or declared."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    book_id: int | None = None

    number: str | None = None
    title: str | None = None
    position: int = Field(default=0, ge=0)
    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)

    structure_source: StructureSource
    declared_confidence: StructureConfidence | None = None
    sections: list[BookSection] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def structure_confidence(self) -> StructureConfidence:
        return self.declared_confidence or CONFIDENCE_BY_SOURCE[self.structure_source]

    @property
    def has_detected_heading(self) -> bool:
        return self.title is not None

    @property
    def is_unlabelled(self) -> bool:
        """True when the document gave neither a title nor a number.

        See :attr:`BookSection.is_unlabelled`: a chapter printed as "Chapter 1"
        has a number and no separate title, which is a real boundary, not an
        unlabelled one.
        """
        return self.title is None and not self.number

    @property
    def location_label(self) -> str | None:
        return _page_range_label(self.start_page, self.end_page)

    def display_title(self) -> str:
        """A label safe to show in the UI. Never an invented heading."""
        if self.title:
            return " ".join(p for p in (self.number, self.title) if p)
        if self.number:
            return f"Chapter {self.number}"
        location = self.location_label
        if location:
            return f"Unlabelled chapter ({location})"
        return f"Unlabelled chapter {self.position + 1}"


class Book(BaseModel):
    """An imported introductory Python textbook."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    title: str = Field(min_length=1, max_length=500)
    #: Only set when the document states it. Never guessed from the filename.
    author: str | None = Field(default=None, max_length=500)

    original_filename: str = Field(min_length=1, max_length=500)
    #: Path of the retained upload, relative to the configured upload directory.
    stored_filename: str | None = Field(default=None, max_length=500)
    source_format: SourceFormat = SourceFormat.BOOK_JSON
    file_size_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, max_length=64)
    #: What the book document was produced from, and by what, for provenance.
    source_filename: str | None = Field(default=None, max_length=500)
    producer: str | None = Field(default=None, max_length=200)

    status: BookStatus = BookStatus.IMPORTED
    page_count: int | None = Field(default=None, ge=0)
    notes: str | None = None
    warnings: list[ExtractionWarning] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=_now)
    imported_at: datetime | None = None

    chapters: list[BookChapter] = Field(default_factory=list)

    @property
    def is_usable_for_grounding(self) -> bool:
        """Whether curriculum extraction and generation may use this book.

        Every stored book validated, so all are usable. Partial ones carry
        declared caveats, and the professor is told so.
        """
        return self.status in (BookStatus.IMPORTED, BookStatus.PARTIAL)


# `BookStructure` was removed with heuristic extraction: the validated
# `app.ingestion.schema.BookDocument` is now the pre-persistence representation,
# and it comes from the input rather than from a parser.
