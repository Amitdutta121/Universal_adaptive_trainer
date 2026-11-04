"""Hybrid chunk ranking through LlamaIndex (Task 11).

LlamaIndex's ``QueryFusionRetriever`` merges our dense cosine ranking with its
``BM25Retriever`` (``bm25s`` with an English stemmer) by reciprocal rank fusion, k = 60,
each side cut to its top ``FUSE_TOP_K``. That stock setup beat our own BM25 + RRF on the gold
set (MRR@10 0.937 vs 0.888, student MRR@5 0.944 vs 0.769; ``docs/RETRIEVAL_BASELINE.md``).

LlamaIndex never embeds here: the dense side is the ranking ``ChunkRetriever`` already
computed, handed over as a fixed retriever. ``num_queries=1`` means no LLM query rewriting,
so fusion makes no model call.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence

#: Results each side contributes before fusion; LlamaIndex's default, and what was measured.
FUSE_TOP_K = 10
#: Two requests importing LlamaIndex at once (two tutorial examples right after a restart) can
#: see a half-imported package and fail with ImportError; the first import is done under this.
_IMPORT_LOCK = threading.Lock()


def fused_ranking(query: str, dense: Sequence[tuple[str, str, float]], *, top_k: int) -> list[str]:
    """Ids from ``dense`` (``(chunk_id, text, cosine)``, best first), reordered by fusion with BM25.

    Chunks with identical text are one LlamaIndex node hash, so only the first survives.
    Deterministic for a fixed ``dense``: both rankings and the fused sort are stable.
    """
    if not dense:
        return []
    # Imported here: LlamaIndex costs about a second to import and only fusion needs it.
    with _IMPORT_LOCK:
        from llama_index.core.base.base_retriever import BaseRetriever
        from llama_index.core.llms import MockLLM
        from llama_index.core.retrievers import QueryFusionRetriever
        from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
        from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
        from llama_index.retrievers.bm25 import BM25Retriever

    nodes = [TextNode(id_=chunk_id, text=text) for chunk_id, text, _ in dense]
    side_k = min(max(FUSE_TOP_K, top_k), len(nodes))

    class _Precomputed(BaseRetriever):
        """The dense ranking ``ChunkRetriever`` already made, cut to ``side_k``."""

        def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
            return [
                NodeWithScore(node=node, score=score)
                for node, (_, _, score) in zip(nodes[:side_k], dense[:side_k], strict=True)
            ]

    fusion = QueryFusionRetriever(
        [_Precomputed(), BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=side_k)],
        llm=MockLLM(),  # never called with num_queries=1; stops a default OpenAI client
        mode=FUSION_MODES.RECIPROCAL_RANK,
        similarity_top_k=top_k,
        num_queries=1,
        use_async=False,
    )
    return [hit.node.node_id for hit in fusion.retrieve(query)]
