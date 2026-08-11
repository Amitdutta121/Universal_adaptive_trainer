"""Source / book ingestion.

Responsibility
    Import professor-supplied **structured book JSON documents**, retain the
    uploaded file, and store the chapters, sections, section text and page ranges
    that curriculum extraction and question generation will ground themselves in.

What this package does not do
    It performs **no extraction**: no heading regular expressions, no font-size
    heuristics, no text segmentation, and no PDF parsing. A book's structure is
    declared by its document. Heuristic extraction was removed because it is not
    deterministic across books -- rules tuned on one textbook silently mis-segment
    the next, and the output still looks plausible, so the failure goes unnoticed.
    See ``docs/DECISIONS.md`` ADR-015 and ADR-016.

    Producing a book JSON document from a raw PDF, EPUB or HTML is out of scope
    for this application. The professor supplies a valid document; this package's
    job is to be uncompromising about validating it.

The section is the unit
    A section is a whole instructional section, never a fixed-size chunk. The
    schema requires non-empty section text and forbids unknown fields, so a
    malformed document is rejected rather than silently reshaped.

Module layout
    ``schema``     the book JSON contract, and its validation
    ``storage``    upload validation and retention of the uploaded document
    ``service``    the workflow: validate, store, persist
    ``retrieval``  reading sections back out with citations

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.persistence``.
    Must not import ``app.generation``, ``app.adaptive`` or ``app.web``.
"""

from app.ingestion.retrieval import SourceRetrieval, chapter_from_row, section_from_row
from app.ingestion.schema import (
    SCHEMA_VERSION,
    BookDocument,
    ChapterInput,
    SectionInput,
    WarningInput,
    parse_book_document,
)
from app.ingestion.service import BookImportService
from app.ingestion.storage import (
    FORMAT_BY_EXTENSION,
    SUPPORTED_EXTENSIONS,
    format_for_filename,
    validate_upload,
)

__all__ = [
    "FORMAT_BY_EXTENSION",
    "SCHEMA_VERSION",
    "SUPPORTED_EXTENSIONS",
    "BookDocument",
    "BookImportService",
    "ChapterInput",
    "SectionInput",
    "SourceRetrieval",
    "WarningInput",
    "chapter_from_row",
    "format_for_filename",
    "parse_book_document",
    "section_from_row",
    "validate_upload",
]
