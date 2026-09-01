"""Semantic retrieval over imported book sections.

Read-only. Given free text or a curriculum subtopic id, return the book sections
most likely to teach it, ranked by dense cosine similarity over the
``section_embeddings`` index. This is the retrieval half of the coverage-page
"Generate" flow, exposed on its own so it can be inspected directly.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.config import get_settings
from app.errors import DomainRuleError
from app.retrieval import SectionEmbeddingStore, SectionRetriever, get_embedder
from app.retrieval.embedder import Embedder
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import RetrievedSectionOut

router = APIRouter(tags=["retrieval"])


def get_query_embedder() -> Embedder:
    """The embedder used for query text. Overridden in tests with a fake."""
    return get_embedder(get_settings())


EmbedderDep = Annotated[Embedder, Depends(get_query_embedder)]


@router.get("/retrieval/sections", response_model=list[RetrievedSectionOut])
def retrieve_sections(
    session: DbSession,
    embedder: EmbedderDep,
    query: Annotated[str | None, Query(description="Free-text query.")] = None,
    subtopic_id: Annotated[
        int | None,
        Query(description="Curriculum subtopic; its topic + name + description becomes the query."),
    ] = None,
    top_k: Annotated[int, Query(ge=1, le=25)] = 5,
) -> list[RetrievedSectionOut]:
    """Rank sections for a query or a subtopic. Exactly one of the two is required."""
    if (query is None) == (subtopic_id is None):
        raise DomainRuleError(
            "Provide exactly one of 'query' or 'subtopic_id'.",
            detail="Pass free text as 'query', or a curriculum subtopic id as 'subtopic_id'.",
        )

    retriever = SectionRetriever(session, SectionEmbeddingStore(session, embedder))
    if subtopic_id is not None:
        results = retriever.for_subtopic(subtopic_id, top_k=top_k)
    else:
        assert query is not None
        results = retriever.search(query, top_k=top_k)
    return [RetrievedSectionOut.from_result(result) for result in results]
