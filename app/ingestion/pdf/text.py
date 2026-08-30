"""LLM-ready text extraction, via ``pymupdf4llm``.

Deliberately not pristine: paragraph reflow, OCR and table structure are out of
scope. A downstream LLM generates questions from this text, so "readable and
roughly right" is the bar, not "typeset accurately" -- see ``docs/DECISIONS.md``
ADR-048.
"""

from __future__ import annotations

import re

import pymupdf
import pymupdf4llm

# `pymupdf4llm` auto-activates its GNN-based layout engine whenever the optional
# `pymupdf-layout` package happens to be installed, and that path is roughly an
# order of magnitude slower for no benefit this package needs (no multi-column
# reading-order recovery is required for a page range already bounded by a
# known chapter/section). Force the plain path so behaviour and latency do not
# depend on what else is installed in the environment. See docs/DECISIONS.md
# ADR-048.
pymupdf4llm.use_layout(False)

_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def extract_pages_markdown(doc: pymupdf.Document) -> list[str]:
    """Per-page markdown text for the whole document, in one pass.

    Calling ``pymupdf4llm.to_markdown`` once *per section* -- rather than once
    for the whole document -- reprocesses shared per-document state (font
    statistics, table detection) on every call; for a book with a rich table of
    contents that turns hundreds of cheap slices into minutes of redundant
    work. ``page_chunks=True`` returns one chunk per page instead, in page
    order, so a section's text is a slice of this single pass, not a call of
    its own.
    """
    chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
    return [chunk["text"] for chunk in chunks]


def join_range(pages: list[str], *, start_page: int, end_page: int) -> str:
    """Join a 1-indexed, inclusive page range from :func:`extract_pages_markdown`."""
    text = "\n\n".join(pages[start_page - 1 : end_page])
    return _EXCESS_BLANK_LINES.sub("\n\n", text).strip()
