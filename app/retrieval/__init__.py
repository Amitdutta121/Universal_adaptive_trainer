"""Semantic retrieval over imported book sections.

``SectionEmbeddingStore`` fills and loads the ``section_embeddings`` index from
``book_sections.text``; ``SectionRetriever`` ranks sections against a free-text
query or against a curriculum subtopic. Dense cosine only -- see
:mod:`app.retrieval.retriever` for why no BM25 or reranker.
"""

from app.retrieval.embedder import (
    DEFAULT_BATCH_SIZE,
    MAX_EMBED_CHARS,
    Embedder,
    OpenRouterEmbedder,
    get_embedder,
)
from app.retrieval.retriever import (
    RetrievedSection,
    SectionRetriever,
    subtopic_query_text,
)
from app.retrieval.store import (
    BackfillResult,
    LoadedVectors,
    SectionEmbeddingStore,
    content_hash,
)

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "MAX_EMBED_CHARS",
    "BackfillResult",
    "Embedder",
    "LoadedVectors",
    "OpenRouterEmbedder",
    "RetrievedSection",
    "SectionEmbeddingStore",
    "SectionRetriever",
    "content_hash",
    "get_embedder",
    "subtopic_query_text",
]
