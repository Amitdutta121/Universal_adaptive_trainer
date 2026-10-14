"""Build the retrieval gold set for the Agah book (tasks/todo.md, Task 1).

Reads the book's imported sections from a database (read-only) and writes
``tests/fixtures/retrieval_gold.json``. Re-running it on the same import gives the same file:

    python -m scripts.build_retrieval_gold                 # the configured DATABASE_URL
    python -m scripts.build_retrieval_gold --db data/adaptive_trainer.db

How each entry is made (the ``source`` field says which):

* ``draft``: a section heading of the import is the query, and its page range is the answer.
  This is the automatic part.
* ``manual``: an entry or a page range checked by hand against the PDF. Its ``manual_edit``
  says why: a section's range that is wrong for its heading, a chapter intro that the import
  lost (pages 10, 22, 50-54, 56, 84-85 are in no section), a curriculum subtopic name, or a
  student-style question.

``relevant_pages`` is the gold answer (1-based PDF pages, as in ``book_sections.start_page``).
Matching is by page overlap, so the set still works after sections become chunks.
``relevant_section_ids`` are the import's sections that overlap those pages. They are for
information only and are ids in the database the script was run on.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.persistence.models import BookRow, BookSectionRow

#: sha256 of Introduction_to_Data_Science_Using_Python_Agah.pdf (Dec 2025 revision, 117 pages).
AGAH_CHECKSUM = "b20cf84ae5cd8e8decc7ec63a8d01d9c904a217e80e1cc9c3345b8f0deeba8dd"
OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "retrieval_gold.json"

#: Section headings used as draft queries. Front matter, practice questions, solutions and
#: references are left out, and so are headings that duplicate a kept one (7.2.1 New File,
#: 14.1.2 Regression).
DRAFT_HEADINGS = [
    "1. Installing Python",
    "2.1. Variables",
    "2.1.1. Boolean Variables",
    "2.1.2. Random Variables",
    "2.2. Strings",
    "2.3. ASCII Code",
    "3.1. Nested Decision Structures",
    "4.1. While Loops",
    "4.2. For Loops",
    "4.4. Nested Loops",
    "5.1. Void and Value Returning Functions",
    "5.2. Passing Data to and From Functions",
    "5.3. Mathematical Built-in Functions",
    "6. Recursion",
    "7.1. Read From a File",
    "7.2. Write to a File",
    "7.2.2. An Existing File",
    "7.3. Notable Built-in Functions",
    "10. Plotting Graphs",
    "11.1 Constructor",
    "11.2 Inheritance",
    "11.3 Polymorphism",
    "12. Using Python Packages",
    "13.1 Networkx",
    "13.2 Matplotlib",
    "14.1 Supervised Learning",
    "14.1.3 Linear Functions",
    "14.1.4 Polynomial Functions",
    "14.2. Unsupervised Learning",
    "15.1 Standardizing Data by Scaling",
    "15.2 T-Test",
]

#: Hand corrections to a draft entry's pages: heading -> (pages, reason).
PAGE_FIXES: dict[str, tuple[list[int], str]] = {
    "2.1.1. Boolean Variables": (
        [13],
        "section runs on into f-string formatting (p14); booleans are only on p13",
    ),
    "2.2. Strings": ([15, 16], "strings continue on p16 (string * int, int(input()))"),
    "4.1. While Loops": ([27, 28, 29], "the while-loop summation example ends on p29"),
    "7.2. Write to a File": ([46, 47], "write() with open(..., 'w') is on p47"),
    "11.1 Constructor": ([65, 66], "first __init__ example is in the chapter intro (p65)"),
    "11.2 Inheritance": ([66, 67], "inheritance example continues on p67"),
    "13.1 Networkx": ([72, 73, 74, 75], "number_of_nodes/remove_edge are on p75"),
    "13.2 Matplotlib": (
        [58, 59, 60, 61, 62, 63, 64, 75, 76],
        "chapter 10 (Plotting Graphs) teaches matplotlib too",
    ),
    "14.1.3 Linear Functions": ([78, 79], "the linregress example is on p79"),
}

_LOST = "chapter intro: these pages are in no imported section"
_SUBTOPIC = "curriculum subtopic name (taxonomy 'Python for Data Science'); pages read from the PDF"
_STUDENT = "student-style question; pages read from the PDF"

#: Entries written by hand: (query, kind, pages, reason).
MANUAL_ENTRIES: list[tuple[str, str, list[int], str]] = [
    ("Introduction to Programming", "heading", [10], _LOST),
    ("Decision Structures", "heading", [22, 23], _LOST),
    ("Lists", "heading", [50, 51, 52, 53, 54], _LOST),
    ("Arrays", "heading", [56], _LOST),
    ("Python and Statistics", "heading", [84, 85], _LOST),
    ("Print statements and formatted printing", "subtopic", [10, 13, 14], _SUBTOPIC),
    ("Arithmetic operators and expression evaluation", "subtopic", [12, 13], _SUBTOPIC),
    ("input() and interactive programs", "subtopic", [12, 16], _SUBTOPIC),
    ("Boolean expressions and comparison operators", "subtopic", [13, 23], _SUBTOPIC),
    ("if-elif-else chains", "subtopic", [24], _SUBTOPIC),
    ("Creating, indexing, and slicing lists", "subtopic", [50], _SUBTOPIC),
    ("List methods (append, insert, remove, sort, len)", "subtopic", [51, 52, 54], _SUBTOPIC),
    ("Variable scope (local vs. global)", "subtopic", [38], _SUBTOPIC),
    ("Accumulator patterns (sum, count, running total)", "subtopic", [28, 29, 31], _SUBTOPIC),
    (
        "Common recursive patterns (factorial, sum, simple traversal)",
        "subtopic",
        [43, 44],
        _SUBTOPIC,
    ),
    ("Opening/reading/closing text files", "subtopic", [45, 46], _SUBTOPIC),
    ("Writing and appending data", "subtopic", [46, 47], _SUBTOPIC),
    ("how do I make a random whole number between 1 and 6?", "student", [15], _STUDENT),
    ("why does '1' + '2' give 12 instead of 3?", "student", [15], _STUDENT),
    ("how do I get the number code for a letter like A?", "student", [20], _STUDENT),
    ("my while loop never stops, why?", "student", [28], _STUDENT),
    ("how does range(5, 0, -1) count down?", "student", [29, 30], _STUDENT),
    ("how many times does the inner loop run in a nested loop?", "student", [33], _STUDENT),
    ("how do I round a number down to an integer?", "student", [40], _STUDENT),
    ("how do I show a number with two decimal places?", "student", [14], _STUDENT),
    (
        "how do I remove the newline at the end of a line I read from a file?",
        "student",
        [47],
        _STUDENT,
    ),
    ("how do I save a list to a file and read it back?", "student", [53], _STUDENT),
    ("what is the difference between a list and a numpy array?", "student", [56], _STUDENT),
    ("how do I draw a pie chart?", "student", [59, 63, 64], _STUDENT),
    ("what does self mean in a class?", "student", [66], _STUDENT),
    ("how do I find which node is most central in a network?", "student", [74], _STUDENT),
    ("how do I fit a straight line through my data?", "student", [78, 79], _STUDENT),
    ("how do I group data points into clusters?", "student", [81, 82], _STUDENT),
    ("how do I find the mean, median and mode of a list?", "student", [84, 85], _STUDENT),
    ("how do I check if two groups are significantly different?", "student", [87, 88], _STUDENT),
]


def heading(section: BookSectionRow) -> str:
    """The heading a section was imported under: its own title, else its chapter's."""
    return section.title or (section.chapter.title if section.chapter else "") or ""


def strip_number(text: str) -> str:
    return re.sub(r"^\d+(\.\d+)*\.?\s+", "", text).strip()


def overlapping(sections: list[BookSectionRow], pages: list[int]) -> list[int]:
    wanted = set(pages)
    return [
        s.id
        for s in sections
        if s.start_page is not None
        and wanted & set(range(s.start_page, (s.end_page or s.start_page) + 1))
    ]


def build(session: Session) -> dict:
    book = session.scalars(
        select(BookRow).where(BookRow.checksum_sha256 == AGAH_CHECKSUM).order_by(BookRow.id)
    ).first()
    if book is None:
        raise SystemExit("The Agah book is not imported in this database.")
    sections = list(
        session.scalars(
            select(BookSectionRow)
            .options(joinedload(BookSectionRow.chapter))
            .where(BookSectionRow.book_id == book.id)
            .order_by(BookSectionRow.position)
        )
    )
    by_heading = {heading(s): s for s in sections}

    entries: list[dict] = []
    for name in DRAFT_HEADINGS:
        section = by_heading.get(name)
        if section is None:
            raise SystemExit(f"Heading not in the import: {name!r}")
        pages = list(range(section.start_page, section.end_page + 1))
        fix = PAGE_FIXES.get(name)
        entries.append(
            {
                "query": strip_number(name),
                "kind": "heading",
                "source": "manual" if fix else "draft",
                "relevant_pages": fix[0] if fix else pages,
                "manual_edit": f"draft pages {pages} -> {fix[0]}: {fix[1]}" if fix else None,
            }
        )
    for query, kind, pages, reason in MANUAL_ENTRIES:
        entries.append(
            {
                "query": query,
                "kind": kind,
                "source": "manual",
                "relevant_pages": pages,
                "manual_edit": reason,
            }
        )

    referenced: set[int] = set()
    for entry in entries:
        ids = overlapping(sections, entry["relevant_pages"])
        entry["relevant_section_ids"] = ids
        referenced.update(ids)

    return {
        "about": (
            "Retrieval gold set, Agah 'Introduction to Data Science Using Python'. "
            "Built by scripts/build_retrieval_gold.py; entries with source=manual were "
            "set or corrected by hand and say why in manual_edit. Matching is by page overlap."
        ),
        "book": {
            "title": book.title,
            "checksum_sha256": AGAH_CHECKSUM,
            "page_count": book.page_count,
            "source_book_id": book.id,
        },
        "sections": {
            str(s.id): {"heading": heading(s), "start_page": s.start_page, "end_page": s.end_page}
            for s in sections
            if s.id in referenced
        },
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", help="SQLite file to read (default: DATABASE_URL)")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    url = f"sqlite:///{Path(args.db).as_posix()}" if args.db else get_settings().database_url
    with Session(create_engine(url)) as session:
        gold = build(session)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(gold, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(gold['entries'])} entries to {args.out}")


if __name__ == "__main__":
    main()
