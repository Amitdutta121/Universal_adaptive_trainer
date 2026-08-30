"""Source / book ingestion.

Responsibility
    Import a professor-supplied **structured book JSON document**, or a raw
    **PDF**, retain the uploaded file, and store the chapters, sections,
    section text and page ranges that curriculum extraction and question
    generation will ground themselves in.

What this package does not do
    Outside :mod:`app.ingestion.pdf`, it performs **no extraction**: no heading
    regular expressions, no font-size heuristics, no text segmentation, and no
    PDF parsing. A book's structure is declared by its document -- a PDF's own
    embedded outline counts as such a declaration (ADR-048), which is why
    reading it is a narrow, confined exception rather than a return to
    heuristic extraction generally. Reading an EPUB or HTML file remains out of
    scope entirely. See ``docs/DECISIONS.md`` ADR-015, ADR-016 and ADR-048.

Module layout
    ``schema``     the book document contract, and its validation
    ``pdf``        turns a raw PDF into that same contract shape (ADR-048)
    ``authoring``  the copy-and-paste instruction that produces a JSON document
    ``library``    rename and delete an imported book
    ``storage``    upload validation and retention of the uploaded document
    ``service``    the workflow: validate (or extract, then validate), store, persist
    ``retrieval``  reading sections back out with citations

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.persistence``.
    Must not import ``app.generation``, ``app.adaptive`` or ``app.web``.
"""

from app.ingestion.authoring import (
    EXAMPLE_DOCUMENT,
    STRUCTURE_SOURCE_TERMS,
    WARNING_CODE_TERMS,
    WARNING_SEVERITY_TERMS,
    VocabularyTerm,
    book_authoring_prompt,
    example_json,
)
from app.ingestion.library import BookLibraryService
from app.ingestion.pdf import extract_book_document
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
    "EXAMPLE_DOCUMENT",
    "FORMAT_BY_EXTENSION",
    "SCHEMA_VERSION",
    "STRUCTURE_SOURCE_TERMS",
    "SUPPORTED_EXTENSIONS",
    "WARNING_CODE_TERMS",
    "WARNING_SEVERITY_TERMS",
    "BookDocument",
    "BookImportService",
    "BookLibraryService",
    "ChapterInput",
    "SectionInput",
    "SourceRetrieval",
    "VocabularyTerm",
    "WarningInput",
    "book_authoring_prompt",
    "chapter_from_row",
    "example_json",
    "extract_book_document",
    "format_for_filename",
    "parse_book_document",
    "section_from_row",
    "validate_upload",
]
