"""Curriculum endpoints: import a fixed taxonomy and read approved structure back.

The application never derives curriculum with an LLM (ADR-021). A valid taxonomy
upload creates an approved version immediately; an invalid one is rejected in
full before any row is written.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.curriculum import TaxonomyImportService, extraction_metadata, proposal_warnings
from app.errors import NotFoundError
from app.persistence.repositories import BookRepository, CurriculumRepository
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    BookSummary,
    CurriculumListResponse,
    CurriculumVersionDetail,
    CurriculumVersionSummary,
    SubtopicDetail,
    SubtopicEvidenceOut,
    SubtopicParent,
    SubtopicSummary,
    TopicOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


@router.get("/versions", response_model=CurriculumListResponse)
def list_versions(session: DbSession, limit: int = 50) -> CurriculumListResponse:
    """Every curriculum version, newest first, plus which one is approved."""
    repo = CurriculumRepository(session)
    approved = repo.get_approved()
    latest = repo.get_latest()
    rows = repo.list_versions(limit=limit)
    return CurriculumListResponse(
        versions=[CurriculumVersionSummary.from_row(row) for row in rows],
        approved_version_id=approved.id if approved else None,
        latest_version_id=latest.id if latest else None,
        total=repo.count(),
    )


@router.post(
    "/versions", response_model=CurriculumVersionDetail, status_code=status.HTTP_201_CREATED
)
def import_taxonomy(
    session: DbSession,
    file: Annotated[UploadFile, File()],
) -> CurriculumVersionDetail:
    """Validate and import a fixed Topic -> Subtopic taxonomy document."""
    data = file.file.read()
    filename = file.filename or "taxonomy.json"
    try:
        version = TaxonomyImportService(session).import_upload(filename=filename, data=data)
    except Exception:
        session.rollback()
        logger.info("Rejected taxonomy upload %r", filename)
        raise
    session.commit()
    return get_version(session, version.id)


@router.get("/approved", response_model=CurriculumVersionDetail)
def get_approved(session: DbSession) -> CurriculumVersionDetail:
    """The curriculum version question generation is allowed to use."""
    approved = CurriculumRepository(session).get_approved()
    if approved is None:
        raise NotFoundError(
            "No curriculum version has been approved yet.",
            detail="Upload a valid taxonomy document first.",
        )
    return get_version(session, approved.id)


@router.get("/versions/{version_id}", response_model=CurriculumVersionDetail)
def get_version(session: DbSession, version_id: int) -> CurriculumVersionDetail:
    """One curriculum version with its full Topic -> Subtopic hierarchy."""
    repo = CurriculumRepository(session)
    version = repo.get_with_tree(version_id)
    books: list[BookSummary] = []
    for book_id in version.source_book_ids or []:
        try:
            books.append(BookSummary.from_row(BookRepository(session).get(int(book_id))))
        except (NotFoundError, ValueError, TypeError):
            # A book removed after a legacy version was created: report what
            # remains rather than failing the whole version.
            continue
    topics = [TopicOut.from_row(topic) for topic in version.topics]
    return CurriculumVersionDetail(
        version=CurriculumVersionSummary.from_row(version),
        topic_count=len(topics),
        subtopic_count=repo.subtopic_count(version_id),
        topics=topics,
        books=books,
        extraction_metadata=extraction_metadata(version.extraction_metadata),
        warnings=proposal_warnings(version.warnings),
    )


@router.get("/subtopics/{subtopic_id}", response_model=SubtopicDetail)
def get_subtopic(session: DbSession, subtopic_id: int) -> SubtopicDetail:
    """One subtopic: its approved definition and any legacy textbook evidence."""
    subtopic = CurriculumRepository(session).get_subtopic(subtopic_id)
    evidence = [SubtopicEvidenceOut.from_row(row) for row in subtopic.evidence]
    return SubtopicDetail(
        subtopic=SubtopicSummary.from_row(subtopic),
        topic=SubtopicParent.from_row(subtopic.topic),
        curriculum_version_id=subtopic.topic.curriculum_version_id,
        is_taxonomy_upload=subtopic.topic.curriculum_version.generated_by == "taxonomy-upload",
        candidate_labels=list(subtopic.candidate_labels or []),
        grouping_reason=subtopic.grouping_reason,
        confidence=subtopic.confidence,
        evidence=evidence,
        book_count=len({item.book_id for item in subtopic.evidence}),
    )
