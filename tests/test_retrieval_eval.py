"""The retrieval gold set and the page-overlap metrics (tasks/todo.md, Tasks 1-2)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.ingestion.service import BookImportService
from app.persistence.repositories import ChunkRepository
from app.retrieval.eval import (
    QueryRun,
    mean_metrics,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    unit_pages,
)

ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = ROOT / "tests" / "fixtures" / "retrieval_gold.json"
AGAH_PDF = ROOT / "books" / "Introduction_to_Data_Science_Using_Python_Agah.pdf"


@pytest.fixture(scope="module")
def gold() -> dict:
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def test_gold_fixture_loads_with_the_agreed_shape(gold: dict) -> None:
    entries = gold["entries"]
    assert len(entries) >= 40
    assert len({e["query"] for e in entries}) == len(entries)
    page_count = gold["book"]["page_count"]
    for entry in entries:
        assert entry["query"].strip()
        assert entry["relevant_pages"], entry["query"]
        assert all(1 <= p <= page_count for p in entry["relevant_pages"]), entry["query"]
        assert isinstance(entry["relevant_section_ids"], list)
        assert all(str(i) in gold["sections"] for i in entry["relevant_section_ids"])
        # Every hand-made or hand-corrected entry says why.
        assert (entry["source"] == "manual") == bool(entry["manual_edit"]), entry["query"]


@pytest.mark.skipif(not AGAH_PDF.is_file(), reason="Agah PDF (books/) not present")
def test_gold_pages_are_covered_by_a_fresh_import(
    gold: dict, session: Session, settings: Settings
) -> None:
    """The gold set is the same file the eval imports, and every query can be answered:
    each entry's relevant pages overlap at least one chunk of a fresh import."""
    book = BookImportService(session, settings).import_upload(
        filename=AGAH_PDF.name, data=AGAH_PDF.read_bytes()
    )
    assert book.checksum_sha256 == gold["book"]["checksum_sha256"]
    assert book.page_count == gold["book"]["page_count"]

    chunks = ChunkRepository(session).list_for_book(book.id)
    assert chunks
    covered = set().union(*(unit_pages(c.page_start, c.page_end) for c in chunks))
    for entry in gold["entries"]:
        assert covered & set(entry["relevant_pages"]), f"no chunk covers {entry['query']!r}"


# -- metrics, on hand-computed cases ----------------------------------------------

RELEVANT = frozenset({10, 11, 12})
#: rank 1 misses, rank 2 hits pages 11-12, rank 3 misses, rank 4 hits page 10.
RANKED = [frozenset({5}), frozenset({11, 12}), frozenset({20}), frozenset({10})]


def test_unit_pages_spans_the_inclusive_range() -> None:
    assert unit_pages(3, 5) == {3, 4, 5}
    assert unit_pages(7, None) == {7}
    assert unit_pages(None, 9) == frozenset()


def test_precision_divides_hits_by_k_even_when_fewer_were_returned() -> None:
    assert precision_at_k(RANKED, RELEVANT, 1) == 0.0
    assert precision_at_k(RANKED, RELEVANT, 3) == pytest.approx(1 / 3)
    assert precision_at_k(RANKED, RELEVANT, 4) == 0.5
    assert precision_at_k([frozenset({10})], RELEVANT, 3) == pytest.approx(1 / 3)


def test_recall_is_the_share_of_relevant_pages_covered() -> None:
    assert recall_at_k(RANKED, RELEVANT, 1) == 0.0
    assert recall_at_k(RANKED, RELEVANT, 3) == pytest.approx(2 / 3)
    assert recall_at_k(RANKED, RELEVANT, 4) == 1.0
    assert recall_at_k([], RELEVANT, 5) == 0.0


def test_reciprocal_rank_of_the_first_hit_within_k() -> None:
    assert reciprocal_rank(RANKED, RELEVANT) == 0.5
    assert reciprocal_rank(RANKED, RELEVANT, 1) == 0.0
    assert reciprocal_rank([frozenset({1})], RELEVANT) == 0.0


def test_ndcg_against_an_ideal_of_the_answerable_units() -> None:
    ideal_two = 1 + 1 / math.log2(3)
    assert ndcg_at_k(RANKED, RELEVANT, 3, 2) == pytest.approx((1 / math.log2(3)) / ideal_two)
    assert ndcg_at_k(RANKED, RELEVANT, 4, 2) == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(5)) / ideal_two
    )
    assert ndcg_at_k([RELEVANT], RELEVANT, 1, 1) == 1.0
    # No unit of the index overlaps the relevant pages: the query cannot be answered.
    assert ndcg_at_k(RANKED, RELEVANT, 4, 0) == 0.0


def test_mean_metrics_averages_over_queries() -> None:
    runs = [
        QueryRun("a", RELEVANT, RANKED, n_relevant_units=2),
        QueryRun("b", RELEVANT, [RELEVANT], n_relevant_units=1),
    ]
    at1 = mean_metrics(runs, [1])[1]
    assert at1 == {"recall": 0.5, "precision": 0.5, "ndcg": 0.5, "mrr": 0.5}
