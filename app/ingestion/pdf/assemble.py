"""Ties outline grouping, text extraction and PDF metadata into one payload.

The only module that combines :mod:`app.ingestion.pdf.outline`,
:mod:`app.ingestion.pdf.fallback` and :mod:`app.ingestion.pdf.text` into the
dict shape :func:`app.ingestion.schema.validate_payload` accepts. See
:func:`app.ingestion.pdf.extract_book_document`, the package's only public
entry point.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from app.errors import InvalidBookDocumentError
from app.ingestion.pdf import fallback
from app.ingestion.pdf import text as text_extraction
from app.ingestion.pdf.outline import GroupedChapter, OutlineEntry, group_outline
from app.ingestion.schema import SCHEMA_VERSION

#: Recorded in the document's ``producer`` field: what made it, for provenance
#: only -- never interpreted, same as any other producer's value.
CONVERTER_NAME = "pymupdf-outline-extractor 1.0"


def build_book_document(doc: pymupdf.Document, *, source_filename: str) -> dict[str, object]:
    """The dict payload ``validate_payload`` accepts, built from an open PDF."""
    entries = [
        OutlineEntry(level=level, title=(title or "").strip(), page=page)
        for level, title, page in doc.get_toc(simple=True)
        if page >= 1
    ]

    pages_markdown = text_extraction.extract_pages_markdown(doc)

    document_warnings: list[dict[str, object]] = []
    if entries:
        structure_source = "pdf_outline"
        chapters = group_outline(entries, page_count=doc.page_count)
    else:
        structure_source = "producer_inferred"
        pages_text = [doc[index].get_text() for index in range(doc.page_count)]
        chapters = fallback.detect_from_page_text(pages_text)
        if chapters:
            message = (
                "This PDF has no embedded table of contents; chapter and section "
                "boundaries were guessed from heading-like text."
            )
        else:
            chapters = fallback.last_resort_split(page_count=doc.page_count)
            message = (
                "No chapter or section markers could be found in this PDF; chapters are "
                "arbitrary page splits."
            )
        document_warnings.append(
            {"code": "producer_inferred_structure", "message": message, "severity": "defect"}
        )

    chapter_payloads: list[dict[str, object]] = []
    for chapter in chapters:
        sections, chapter_is_empty = _section_payloads(pages_markdown, chapter, structure_source)
        if chapter_is_empty:
            document_warnings.append(
                {
                    "code": "source_text_unreadable",
                    "message": (
                        f"Pages {chapter.start_page}-{chapter.end_page} had no extractable "
                        "text on any page and were dropped."
                    ),
                    "severity": "defect",
                }
            )
            continue
        chapter_payloads.append(
            {
                "title": chapter.title,
                "start_page": chapter.start_page,
                "end_page": chapter.end_page,
                "structure_source": structure_source,
                "sections": sections,
            }
        )

    if not chapter_payloads:
        raise InvalidBookDocumentError(
            "This PDF's pages had no extractable text.",
            detail=(
                "Every candidate chapter was empty. This is likely a scanned book with no "
                "text layer; optical character recognition is not supported."
            ),
        )

    metadata_title = str(doc.metadata.get("title") or "").strip()
    title = metadata_title or Path(source_filename).stem
    if not metadata_title:
        document_warnings.append(
            {
                "code": "metadata_unavailable",
                "message": "The PDF did not state a title; the filename was used instead.",
                "severity": "info",
            }
        )
    author = str(doc.metadata.get("author") or "").strip() or None

    return {
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "author": author,
        "source_filename": source_filename,
        "producer": CONVERTER_NAME,
        "page_count": doc.page_count,
        "chapters": chapter_payloads,
        "warnings": document_warnings,
    }


def _section_payloads(
    pages_markdown: list[str], chapter: GroupedChapter, structure_source: str
) -> tuple[list[dict[str, object]], bool]:
    """One chapter's sections as schema-shaped dicts.

    A section with no extractable text (an image-only page, a TOC entry
    pointing at a divider) is never emitted empty -- the schema forbids that.
    Its page range is folded into the section that produces text next, or, if
    it was the last one, into the section before it. Returns ``(sections,
    chapter_is_empty)``; the caller drops the whole chapter and warns at the
    document level when every one of its sections was unreadable.
    """
    payloads: list[dict[str, object]] = []
    carry_start: int | None = None
    swallowed_ranges: list[str] = []

    for section in chapter.sections:
        start = carry_start if carry_start is not None else section.start_page
        body = text_extraction.join_range(
            pages_markdown, start_page=start, end_page=section.end_page
        )
        if not body:
            carry_start = start
            swallowed_ranges.append(f"{section.start_page}-{section.end_page}")
            continue

        payload: dict[str, object] = {
            "title": section.title,
            "start_page": start,
            "end_page": section.end_page,
            "text": body,
            "structure_source": structure_source,
        }
        if swallowed_ranges:
            payload["warnings"] = [_unreadable_warning(swallowed_ranges)]
            swallowed_ranges = []
        payloads.append(payload)
        carry_start = None

    if carry_start is not None:
        if not payloads:
            return [], True
        payloads[-1]["end_page"] = chapter.end_page
        payloads[-1].setdefault("warnings", []).append(_unreadable_warning(swallowed_ranges))  # type: ignore[union-attr]

    return payloads, False


def _unreadable_warning(page_ranges: list[str]) -> dict[str, object]:
    return {
        "code": "source_text_unreadable",
        "message": (
            f"No text could be extracted from pages {', '.join(page_ranges)}; they are "
            "folded into this section."
        ),
        "severity": "defect",
    }
