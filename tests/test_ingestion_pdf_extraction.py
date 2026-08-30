"""Extraction against real textbook PDFs (books/*.pdf).

Not exhaustive -- ``tests/test_ingestion_pdf_outline.py`` covers the grouping
algorithm's edge cases directly with synthetic data. This is a sanity check
that real PDFs produce a valid, plausible ``BookDocument``, covering both the
primary path (a real embedded outline) and the no-outline fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.enums import StructureSource
from app.ingestion.pdf import extract_book_document

BOOKS_DIR = Path(__file__).resolve().parent.parent / "books"

pytestmark = pytest.mark.skipif(
    not BOOKS_DIR.is_dir(), reason="sample PDF corpus (books/) not present"
)


def _load(name: str):
    data = (BOOKS_DIR / name).read_bytes()
    return extract_book_document(data, source_filename=name)


def test_a_book_with_a_real_outline_is_extracted_cleanly() -> None:
    document = _load("thinkpython2.pdf")
    assert len(document.chapters) > 1
    assert document.section_count > 1
    assert document.is_partial() is False
    assert document.chapters[0].sections[0].structure_source is StructureSource.PDF_OUTLINE
    assert all(section.text.strip() for section in document.sections)


def test_a_book_with_no_outline_falls_back_and_is_marked_partial() -> None:
    document = _load("invent_with_python.pdf")
    assert len(document.chapters) >= 1
    assert document.is_partial() is True
    assert document.chapters[0].structure_source is StructureSource.PRODUCER_INFERRED
    assert document.declared_defects()
