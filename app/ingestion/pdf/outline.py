"""Grouping of chapter/section boundaries into a two-level tree with page ranges.

Shared by the primary path (a PDF's own outline, via ``get_toc()``) and the
regex fallback (:mod:`app.ingestion.pdf.fallback`) for a PDF with no outline:
both reduce to the same problem -- an ordered list of ``(page, title,
is_chapter)`` boundaries -- and the page-range arithmetic must behave
identically for either to be trustworthy. No PyMuPDF import here, so it is
unit-testable with plain data (see ``tests/test_ingestion_pdf_outline.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OutlineEntry:
    """One row of ``Document.get_toc(simple=True)``: ``[level, title, page]``."""

    level: int
    title: str
    page: int  # 1-indexed, as PyMuPDF reports it


@dataclass(frozen=True)
class GroupedSection:
    title: str | None
    start_page: int
    end_page: int


@dataclass
class GroupedChapter:
    title: str | None
    start_page: int
    end_page: int
    sections: list[GroupedSection] = field(default_factory=list)


def group_outline(entries: list[OutlineEntry], *, page_count: int) -> list[GroupedChapter]:
    """Group a PDF's own outline entries.

    Level 1 is a chapter; every deeper level collapses onto one section tier,
    matching the schema's exactly-two-level shape.
    """
    boundaries = [(entry.page, entry.title, entry.level == 1) for entry in entries]
    return group_boundaries(boundaries, page_count=page_count)


def group_boundaries(
    boundaries: list[tuple[int, str | None, bool]], *, page_count: int
) -> list[GroupedChapter]:
    """Group ``(page, title, is_chapter)`` triples, in document order.

    A chapter's range runs to the next chapter-level boundary -- its own
    sections do not end it; a section's range runs to the very next boundary
    of either kind. A boundary with no preceding chapter is promoted to be a
    chapter in its own right, so a leading section is never dropped for
    lacking a parent. A chapter left with no sections synthesizes one spanning
    its own range, matching the schema's "at least one section" rule without
    fabricating a title.
    """
    if not boundaries:
        return []

    chapters: list[GroupedChapter] = []
    for index, (page, title, is_chapter) in enumerate(boundaries):
        section_end = _end_page(boundaries, index, page_count=page_count, chapters_only=False)
        if is_chapter:
            chapter_end = _end_page(boundaries, index, page_count=page_count, chapters_only=True)
            chapters.append(GroupedChapter(title=title, start_page=page, end_page=chapter_end))
        elif not chapters:
            chapter_end = _end_page(boundaries, index, page_count=page_count, chapters_only=True)
            chapter = GroupedChapter(title=title, start_page=page, end_page=chapter_end)
            chapter.sections.append(
                GroupedSection(title=title, start_page=page, end_page=section_end)
            )
            chapters.append(chapter)
        else:
            chapters[-1].sections.append(
                GroupedSection(title=title, start_page=page, end_page=section_end)
            )

    for chapter in chapters:
        if not chapter.sections:
            chapter.sections.append(
                GroupedSection(title=None, start_page=chapter.start_page, end_page=chapter.end_page)
            )
    return chapters


def _end_page(
    boundaries: list[tuple[int, str | None, bool]],
    index: int,
    *,
    page_count: int,
    chapters_only: bool,
) -> int:
    """The last page before whichever later boundary closes this one's range.

    Clamped to never run backwards, so two boundaries stamped on the same page
    (a common front-matter artifact) still produce a valid one-page range.
    """
    start = boundaries[index][0]
    for later_page, _title, later_is_chapter in boundaries[index + 1 :]:
        if chapters_only and not later_is_chapter:
            continue
        return max(later_page - 1, start)
    return max(page_count, start)
