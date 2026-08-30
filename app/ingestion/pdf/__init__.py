"""PDF book import: the only place in this application that reads a PDF.

Public entry point: :func:`extract_book_document`. Everywhere else in this
codebase, book structure is still declared by the input (ADR-015) -- a PDF's
own embedded outline *is* that declaration (the publisher's own table of
contents), which is why its units are stamped ``pdf_outline`` at HIGH
confidence rather than treated as a guess. Only the no-outline fallback
guesses, and it is stamped ``producer_inferred``/LOW, which makes the book
``PARTIAL`` exactly like any other caveated document (ADR-012). See
``docs/DECISIONS.md`` ADR-048.

Module layout
    ``outline``   pure page-range grouping of ``(page, title, is_chapter)``
                  boundaries, shared by the outline and fallback paths
    ``fallback``  regex heading detection, used only when a PDF has no outline
    ``text``      per-page-range markdown extraction via ``pymupdf4llm``
    ``assemble``  ties the above into the dict :func:`app.ingestion.schema.
                  validate_payload` accepts

``pymupdf``/``pymupdf4llm`` are declared dependencies confined to this package;
``tests/test_boundaries.py`` asserts nothing outside it imports either.
"""

from __future__ import annotations

import pymupdf

from app.errors import InvalidBookDocumentError
from app.ingestion.pdf.assemble import build_book_document
from app.ingestion.schema import BookDocument, validate_payload

__all__ = ["extract_book_document"]


def extract_book_document(data: bytes, *, source_filename: str) -> BookDocument:
    """Derive a validated :class:`BookDocument` from raw PDF bytes.

    Raises:
        InvalidBookDocumentError: the bytes are not a readable PDF, or every
            page turned out to have no extractable text.
    """
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # pymupdf raises its own, undocumented exception types
        raise InvalidBookDocumentError(
            "This file could not be read as a PDF.",
            detail=str(exc),
        ) from exc

    try:
        payload = build_book_document(doc, source_filename=source_filename)
    finally:
        doc.close()

    return validate_payload(payload)
