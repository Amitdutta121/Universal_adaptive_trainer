"""Pure page-range grouping for a PDF's outline (no PyMuPDF import needed).

This is the algorithm both the primary path (a real outline) and the regex
fallback share -- see ``app.ingestion.pdf.outline``.
"""

from __future__ import annotations

from app.ingestion.pdf.outline import GroupedSection, OutlineEntry, group_outline


def test_a_childless_chapter_gets_one_synthesized_section() -> None:
    chapters = group_outline(
        [
            OutlineEntry(level=1, title="Intro", page=1),
            OutlineEntry(level=1, title="Next", page=10),
        ],
        page_count=20,
    )
    assert len(chapters) == 2
    assert chapters[0].start_page == 1
    assert chapters[0].end_page == 9
    assert chapters[0].sections == [GroupedSection(title=None, start_page=1, end_page=9)]


def test_sections_nest_under_the_preceding_chapter() -> None:
    entries = [
        OutlineEntry(level=1, title="Ch1", page=1),
        OutlineEntry(level=2, title="1.1", page=1),
        OutlineEntry(level=2, title="1.2", page=5),
        OutlineEntry(level=1, title="Ch2", page=10),
    ]
    chapters = group_outline(entries, page_count=20)
    assert len(chapters) == 2
    assert [s.title for s in chapters[0].sections] == ["1.1", "1.2"]
    assert chapters[0].sections[0].end_page == 4
    assert chapters[0].sections[1].end_page == 9
    assert chapters[0].end_page == 9


def test_deeper_levels_collapse_onto_the_section_tier() -> None:
    entries = [
        OutlineEntry(level=1, title="Ch1", page=1),
        OutlineEntry(level=2, title="1.1", page=1),
        OutlineEntry(level=3, title="1.1.1", page=2),
    ]
    chapters = group_outline(entries, page_count=10)
    assert len(chapters) == 1
    assert [s.title for s in chapters[0].sections] == ["1.1", "1.1.1"]


def test_two_entries_on_the_same_page_do_not_produce_a_backwards_range() -> None:
    entries = [
        OutlineEntry(level=1, title="Cover", page=1),
        OutlineEntry(level=1, title="Ch1", page=1),
    ]
    chapters = group_outline(entries, page_count=10)
    assert chapters[0].start_page == 1
    assert chapters[0].end_page == 1
    assert chapters[0].end_page >= chapters[0].start_page


def test_the_last_chapter_runs_to_the_end_of_the_book() -> None:
    entries = [
        OutlineEntry(level=1, title="Ch1", page=1),
        OutlineEntry(level=1, title="Ch2", page=10),
    ]
    chapters = group_outline(entries, page_count=42)
    assert chapters[1].end_page == 42


def test_a_leading_section_with_no_chapter_is_promoted() -> None:
    """A boundary is never dropped for lacking a fictitious parent."""
    entries = [
        OutlineEntry(level=2, title="Preface", page=1),
        OutlineEntry(level=1, title="Ch1", page=5),
    ]
    chapters = group_outline(entries, page_count=20)
    assert len(chapters) == 2
    assert chapters[0].title == "Preface"
    assert chapters[0].end_page == 4
    assert [s.title for s in chapters[0].sections] == ["Preface"]


def test_no_entries_produces_no_chapters() -> None:
    assert group_outline([], page_count=10) == []
