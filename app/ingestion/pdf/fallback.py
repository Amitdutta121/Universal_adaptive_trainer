"""Heuristic chapter/section detection for a PDF with no embedded outline.

Deliberately narrow: two regular expressions over each page's plain text,
nothing else -- no font-size comparison, no layout analysis. Every unit this
module produces is ``StructureSource.PRODUCER_INFERRED`` (LOW confidence): this
is the guess ADR-012 says must be marked, never smoothed over. The bar is "the
professor has something to select", not "correct" -- a document this heuristic
gets wrong is still visibly ``PARTIAL``, not silently broken.
"""

from __future__ import annotations

import re

from app.ingestion.pdf.outline import GroupedChapter, group_boundaries

_CHAPTER_HEADING = re.compile(r"^(chapter|part)\s+\d+\b", re.IGNORECASE)
_SECTION_HEADING = re.compile(r"^\d+\.\d+(\.\d+)?\s+\S")

#: Size of a last-resort split block, when no heading pattern matched at all.
_LAST_RESORT_PAGES_PER_CHAPTER = 20


def detect_from_page_text(pages: list[str]) -> list[GroupedChapter]:
    """``pages[i]`` is the plain text of 1-indexed page ``i + 1``.

    Returns an empty list, never a placeholder chapter, when nothing matched --
    the caller falls back to :func:`last_resort_split` in that case.
    """
    boundaries: list[tuple[int, str, bool]] = []
    for page_number, text in enumerate(pages, start=1):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _CHAPTER_HEADING.match(stripped):
                boundaries.append((page_number, stripped[:200], True))
                break
            if _SECTION_HEADING.match(stripped):
                boundaries.append((page_number, stripped[:200], False))
                break

    if not boundaries:
        return []
    return group_boundaries(boundaries, page_count=len(pages))


def last_resort_split(*, page_count: int) -> list[GroupedChapter]:
    """No heading pattern matched anywhere: fixed-size page blocks.

    Purely so the chapter picker has *something* to select -- never claimed as
    real structure. The caller marks every unit LOW confidence with an
    explicit, document-level warning regardless of this function's output.
    """
    if page_count <= 0:
        return []
    boundaries: list[tuple[int, str | None, bool]] = [
        (start, None, True) for start in range(1, page_count + 1, _LAST_RESORT_PAGES_PER_CHAPTER)
    ]
    return group_boundaries(boundaries, page_count=page_count)
