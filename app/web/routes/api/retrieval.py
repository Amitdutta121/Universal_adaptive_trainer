"""Semantic retrieval over imported book sections.

Read-only. Given free text or a curriculum subtopic id, return the book sections
most likely to teach it, ranked by dense cosine similarity over the
``section_embeddings`` index. This is the retrieval half of the coverage-page
"Generate" flow, exposed on its own so it can be inspected directly.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.config import get_settings
from app.errors import DomainRuleError
from app.persistence.models import BookRow
from app.persistence.repositories import CurriculumRepository
from app.retrieval import SectionEmbeddingStore, SectionRetriever, get_embedder
from app.retrieval.embedder import Embedder
from app.web.routes.api.deps import CourseScope, DbSession, ensure_in_course
from app.web.routes.api.schemas import RetrievedSectionOut

router = APIRouter(tags=["retrieval"])


def get_query_embedder() -> Embedder:
    """The embedder used for query text. Overridden in tests with a fake."""
    return get_embedder(get_settings())


EmbedderDep = Annotated[Embedder, Depends(get_query_embedder)]


@router.get("/retrieval/sections", response_model=list[RetrievedSectionOut])
def retrieve_sections(
    session: DbSession,
    course: CourseScope,
    embedder: EmbedderDep,
    query: Annotated[str | None, Query(description="Free-text query.")] = None,
    subtopic_id: Annotated[
        int | None,
        Query(description="Curriculum subtopic; its topic + name + description becomes the query."),
    ] = None,
    top_k: Annotated[int, Query(ge=1, le=25)] = 5,
) -> list[RetrievedSectionOut]:
    """Rank the course's sections for a query or a subtopic. Exactly one is required."""
    if (query is None) == (subtopic_id is None):
        raise DomainRuleError(
            "Provide exactly one of 'query' or 'subtopic_id'.",
            detail="Pass free text as 'query', or a curriculum subtopic id as 'subtopic_id'.",
        )

    book_ids = (
        list(session.scalars(select(BookRow.id).where(BookRow.course_id == course)))
        if course is not None
        else None
    )
    retriever = SectionRetriever(session, SectionEmbeddingStore(session, embedder))
    if subtopic_id is not None:
        subtopic = CurriculumRepository(session).get_subtopic(subtopic_id)
        ensure_in_course(
            subtopic.topic.curriculum_version.course_id, course, f"Subtopic {subtopic_id}"
        )
        results = retriever.for_subtopic(subtopic_id, top_k=top_k, book_ids=book_ids)
    else:
        assert query is not None
        results = retriever.search(query, top_k=top_k, book_ids=book_ids)
    return [RetrievedSectionOut.from_result(result) for result in results]
