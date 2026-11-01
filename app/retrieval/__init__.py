"""Semantic retrieval over imported book chunks.

``ChunkEmbeddingStore`` fills and loads ``chunk_embeddings`` (one vector per chunk and
embedding model); ``ChunkRetriever`` ranks a book's current chunks against a free-text
query or a curriculum subtopic, by dense cosine. See :mod:`app.retrieval.chunks`.
"""

from app.retrieval.chunks import (
    ChunkEmbeddingStore,
    ChunkRetriever,
    RetrievedChunk,
    subtopic_query_text,
)
from app.retrieval.embedder import (
    DEFAULT_BATCH_SIZE,
    MAX_EMBED_CHARS,
    Embedder,
    OpenRouterEmbedder,
    get_embedder,
)

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "MAX_EMBED_CHARS",
    "ChunkEmbeddingStore",
    "ChunkRetriever",
    "Embedder",
    "OpenRouterEmbedder",
    "RetrievedChunk",
    "get_embedder",
    "subtopic_query_text",
]
