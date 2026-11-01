"""Retrieval metrics scored by page overlap, with no LLM judge.

A retrieved unit (a section today, a chunk later) is a *hit* when its pages overlap the
gold set's ``relevant_pages``. Scoring by pages instead of ids lets one gold set score
any unit granularity. Standard definitions, binary relevance:

* precision@k: hits in the top k, divided by k
* recall@k: the share of relevant pages covered by the top k
* MRR: 1 / rank of the first hit (0 when there is none)
* nDCG@k: DCG with gain 1 per hit, divided by the DCG of an ideal ranking. The ideal
  ranking puts every unit of the index that overlaps the relevant pages first,
  ``min(k, n_relevant_units)`` of them. A query that no unit can answer scores 0.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

Pages = frozenset[int]


def unit_pages(start_page: int | None, end_page: int | None) -> Pages:
    if start_page is None:
        return frozenset()
    return frozenset(range(start_page, (end_page or start_page) + 1))


def is_hit(pages: Pages, relevant: Pages) -> bool:
    return not pages.isdisjoint(relevant)


def precision_at_k(ranked: Sequence[Pages], relevant: Pages, k: int) -> float:
    return sum(is_hit(p, relevant) for p in ranked[:k]) / k


def recall_at_k(ranked: Sequence[Pages], relevant: Pages, k: int) -> float:
    if not relevant:
        return 0.0
    covered = frozenset().union(*ranked[:k]) if ranked[:k] else frozenset()
    return len(covered & relevant) / len(relevant)


def reciprocal_rank(ranked: Sequence[Pages], relevant: Pages, k: int | None = None) -> float:
    for rank, pages in enumerate(ranked[:k] if k else ranked, start=1):
        if is_hit(pages, relevant):
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked: Sequence[Pages], relevant: Pages, k: int, n_relevant_units: int) -> float:
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(k, n_relevant_units)))
    if ideal == 0.0:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, p in enumerate(ranked[:k]) if is_hit(p, relevant))
    return dcg / ideal


@dataclass(frozen=True)
class QueryRun:
    """One gold query and what the retriever returned for it, best first."""

    query: str
    relevant: Pages
    ranked: Sequence[Pages]
    n_relevant_units: int


def mean_metrics(runs: Iterable[QueryRun], ks: Sequence[int]) -> dict[int, dict[str, float]]:
    """``{k: {"recall", "precision", "ndcg", "mrr"}}`` averaged over the runs."""
    runs = list(runs)
    if not runs:
        return {k: {"recall": 0.0, "precision": 0.0, "ndcg": 0.0, "mrr": 0.0} for k in ks}
    n = len(runs)
    return {
        k: {
            "recall": sum(recall_at_k(r.ranked, r.relevant, k) for r in runs) / n,
            "precision": sum(precision_at_k(r.ranked, r.relevant, k) for r in runs) / n,
            "ndcg": sum(ndcg_at_k(r.ranked, r.relevant, k, r.n_relevant_units) for r in runs) / n,
            "mrr": sum(reciprocal_rank(r.ranked, r.relevant, k) for r in runs) / n,
        }
        for k in ks
    }
