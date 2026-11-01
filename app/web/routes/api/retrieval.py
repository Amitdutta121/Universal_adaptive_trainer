"""A book's chunks, and semantic retrieval over them.

``GET /chunks`` lists a book's current chunks (optionally those covering one page) and
``GET /chunks/{id}`` reads one of any version; ``GET /chunks/outline`` lists a book's chunks
without their text, for a picker. ``GET /chunks/search`` ranks chunks for
free text or a curriculum subtopic by dense cosine over ``chunk_embeddings`` -- the
retrieval half of the coverage-page "Generate" flow, exposed so it can be inspected.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.config import get_settings
from app.errors import DomainRuleError
from app.ingestion import SourceRetrieval
from app.persistence.repositories import BookRepository, CurriculumRepository, QuestionRepository
from app.retrieval import get_embedder
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever, course_book_ids
from app.retrieval.embedder import Embedder
from app.web.routes.api.deps import SPENDS_LLM_CREDIT, CourseScope, DbSession, ensure_in_course
from app.web.routes.api.schemas import (
    BookSummary,
    ChunkListResponse,
    ChunkOut,
    ChunkOutlineEntry,
    ChunkOutlineResponse,
    ChunkSummary,
    RetrievedChunkOut,
)

router = APIRouter(tags=["retrieval"])


def get_query_embedder() -> Embedder:
    """The embedder used for query text. Overridden in tests with a fake."""
    return get_embedder(get_settings())


EmbedderDep = Annotated[Embedder, Depends(get_query_embedder)]


@router.get("/chunks", response_model=ChunkListResponse)
def list_chunks(
    session: DbSession,
    course: CourseScope,
    book_id: int,
    page: Annotated[int | None, Query(ge=1, description="Only chunks covering this page.")] = None,
) -> ChunkListResponse:
    """A book's current chunks in reading order, or just those covering one page."""
    ensure_in_course(BookRepository(session).get(book_id).course_id, course, f"Book {book_id}")
    chunks = SourceRetrieval(session).chunks_in_book(book_id, page=page)
    return ChunkListResponse(
        chunks=[ChunkOut.from_chunk(chunk) for chunk in chunks], total=len(chunks)
    )


@router.get(
    "/chunks/search",
    response_model=list[RetrievedChunkOut],
    dependencies=SPENDS_LLM_CREDIT,
)
def search_chunks(
    session: DbSession,
    course: CourseScope,
    embedder: EmbedderDep,
    q: Annotated[str | None, Query(description="Free-text query.")] = None,
    subtopic_id: Annotated[
        int | None,
        Query(description="Curriculum subtopic; its topic + name + description becomes the query."),
    ] = None,
    book_id: Annotated[int | None, Query(description="Search this book only.")] = None,
    top_k: Annotated[int, Query(ge=1, le=25)] = 5,
) -> list[RetrievedChunkOut]:
    """Rank the course's current chunks for a query or a subtopic. Exactly one is required.

    Embeds any chunk still missing a vector in the configured model first.
    """
    if (q is None) == (subtopic_id is None):
        raise DomainRuleError(
            "Provide exactly one of 'q' or 'subtopic_id'.",
            detail="Pass free text as 'q', or a curriculum subtopic id as 'subtopic_id'.",
        )
    book_ids = course_book_ids(session, course)
    if book_id is not None:
        ensure_in_course(BookRepository(session).get(book_id).course_id, course, f"Book {book_id}")
        book_ids = [book_id]
    retriever = ChunkRetriever(session, ChunkEmbeddingStore(session, embedder))
    if subtopic_id is not None:
        subtopic = CurriculumRepository(session).get_subtopic(subtopic_id)
        ensure_in_course(
            subtopic.topic.curriculum_version.course_id, course, f"Subtopic {subtopic_id}"
        )
        results = retriever.for_subtopic(subtopic_id, top_k=top_k, book_ids=book_ids)
    else:
        assert q is not None
        results = retriever.search(q, top_k=top_k, book_ids=book_ids)
    return [RetrievedChunkOut.from_result(result) for result in results]


# Declared before "/chunks/{chunk_id}", which would otherwise read "outline" as a chunk id.
@router.get("/chunks/outline", response_model=ChunkOutlineResponse)
def chunk_outline(session: DbSession, course: CourseScope, book_id: int) -> ChunkOutlineResponse:
    """A book's current chunks without their text, each with the questions it has produced.

    What a chunk picker lists; grouping by heading is the client's (ADR-066).
    """
    book = BookRepository(session).get(book_id)
    ensure_in_course(book.course_id, course, f"Book {book_id}")
    produced = QuestionRepository(session).count_by_source_chunk()
    return ChunkOutlineResponse(
        book=BookSummary.from_row(book),
        chunks=[
            ChunkOutlineEntry(
                chunk=ChunkSummary.from_chunk(chunk),
                existing_question_count=produced.get(chunk.id, 0),
            )
            for chunk in SourceRetrieval(session).chunks_in_book(book_id)
        ],
    )


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
def get_chunk(session: DbSession, course: CourseScope, chunk_id: str) -> ChunkOut:
    """One chunk of any version: its text plus the citation that makes it traceable."""
    chunk = SourceRetrieval(session).get_chunk(chunk_id)
    ensure_in_course(BookRepository(session).get(chunk.book_id).course_id, course, "Chunk")
    return ChunkOut.from_chunk(chunk)
