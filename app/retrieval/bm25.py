"""Lexical ranking and rank fusion for hybrid chunk retrieval (Task 11).

BM25 catches what embeddings blur: code tokens and exact names (``randint``, ``rstrip``,
``ord``) in student questions. Reciprocal rank fusion merges it with the dense ranking
using ranks only, so the two score scales never need calibrating against each other.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import TypeVar

import bm25s
import numpy as np

T = TypeVar("T", bound=Hashable)

#: The usual RRF constant (Cormack et al., 2009); damps the weight of the very top ranks.
RRF_K = 60


def bm25_ranking(corpus: Sequence[str], query: str) -> list[int]:
    """Indices of ``corpus`` documents sharing a term with ``query``, best BM25 first.

    Documents with no query term are left out rather than ranked last. Ties keep corpus
    order, so the ranking is deterministic for a fixed corpus.
    """
    if not corpus:
        return []
    index = bm25s.BM25()
    index.index(
        bm25s.tokenize(list(corpus), stopwords="en", show_progress=False), show_progress=False
    )
    terms = bm25s.tokenize([query], stopwords="en", show_progress=False, return_ids=False)[0]
    if not terms:
        return []
    scores = index.get_scores(terms)
    order = np.argsort(-scores, kind="stable")
    return [int(i) for i in order if scores[i] > 0]


def reciprocal_rank_fusion(rankings: Sequence[Sequence[T]], *, k: int = RRF_K) -> list[T]:
    """Items of every ranking ordered by ``sum(1 / (k + rank))``, rank counted from 1.

    An item missing from a ranking gets nothing from it. Ties go to the item seen first
    (earlier ranking, then earlier rank), so the result is deterministic.
    """
    scores: dict[T, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda item: -scores[item])
