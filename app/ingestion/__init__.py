"""Source / book ingestion.

Responsibility
    Import a professor-supplied book file (PDF, DOCX or PPTX), retain the upload, and
    store it as versioned chunks -- each with its pages and heading path -- that
    retrieval, question generation and citations ground themselves in.

Module layout
    ``parsing``    turns a file into chunks: Docling, or PDF page text (Task 5)
    ``library``    rename and delete an imported book
    ``storage``    upload validation and retention of the uploaded file
    ``service``    the workflow: check, parse, store a new book or a new version
    ``retrieval``  reading chunks back out with citations

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.persistence``.
    Must not import ``app.generation``, ``app.adaptive`` or ``app.web``.
"""

from app.ingestion.library import BookLibraryService
from app.ingestion.retrieval import SourceRetrieval, chunk_from_row
from app.ingestion.service import BookImportService
from app.ingestion.storage import (
    FORMAT_BY_EXTENSION,
    SUPPORTED_EXTENSIONS,
    format_for_filename,
    validate_upload,
)

__all__ = [
    "FORMAT_BY_EXTENSION",
    "SUPPORTED_EXTENSIONS",
    "BookImportService",
    "BookLibraryService",
    "SourceRetrieval",
    "chunk_from_row",
    "format_for_filename",
    "validate_upload",
]
