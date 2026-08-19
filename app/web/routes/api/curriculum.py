"""Curriculum endpoints: import a fixed taxonomy, read it back, and manage it.

The application never derives curriculum with an LLM (ADR-021). A valid taxonomy
upload creates an approved version immediately; an invalid one is rejected in
full before any row is written.

After the upload, a version's display names can be edited and a version can be
deleted (ADR-046). Neither touches structure: which topics exist, and which
subtopics hang off which topic, is what the document declared.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.config import get_settings
from app.curriculum import (
    ALL_FIELDS,
    SCHEMA_VERSION,
    SUPPORTED_EXTENSIONS,
    CurriculumLibraryService,
    TaxonomyImportService,
    example_json,
    extraction_metadata,
    proposal_warnings,
    taxonomy_authoring_prompt,
)
from app.errors import NotFoundError
from app.persistence.repositories import BookRepository, CurriculumRepository
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    BookSummary,
    CurriculumItemLabelUpdate,
    CurriculumListResponse,
    CurriculumVersionDeletion,
    CurriculumVersionDetail,
    CurriculumVersionLabelUpdate,
    CurriculumVersionSummary,
    CurriculumVersionUsage,
    FieldLimitOut,
    SubtopicDetail,
    SubtopicEvidenceOut,
    SubtopicParent,
    SubtopicSummary,
    TaxonomyDocumentGuide,
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
    # One grouped query for the whole page rather than a count per row.
    counts = repo.subtopic_counts_for([row.id for row in rows])
    return CurriculumListResponse(
        versions=[
            CurriculumVersionSummary.from_row(row, subtopic_count=counts.get(row.id, 0))
            for row in rows
        ],
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


@router.get("/document-guide", response_model=TaxonomyDocumentGuide)
def document_guide() -> TaxonomyDocumentGuide:
    """What a valid taxonomy document is, and the prompt that produces one.

    Rendered from the taxonomy contract rather than written out here, so a client
    cannot describe a document this application would refuse. The prompt is
    advisory: it grants nothing, and every upload is still validated in full.
    """
    settings = get_settings()
    return TaxonomyDocumentGuide(
        schema_version=SCHEMA_VERSION,
        supported_extensions=list(SUPPORTED_EXTENSIONS),
        max_upload_mb=settings.max_book_upload_mb,
        prompt=taxonomy_authoring_prompt(max_upload_mb=settings.max_book_upload_mb),
        example_json=example_json(),
        fields=FieldLimitOut.from_limits(ALL_FIELDS),
    )


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
    subtopic_count = repo.subtopic_count(version_id)
    return CurriculumVersionDetail(
        version=CurriculumVersionSummary.from_row(version, subtopic_count=subtopic_count),
        topic_count=len(topics),
        subtopic_count=subtopic_count,
        topics=topics,
        books=books,
        extraction_metadata=extraction_metadata(version.extraction_metadata),
        warnings=proposal_warnings(version.warnings),
        usage=CurriculumVersionUsage.from_usage(
            CurriculumLibraryService(session).usage(version_id)
        ),
    )


@router.patch("/versions/{version_id}", response_model=CurriculumVersionDetail)
def update_version(
    session: DbSession, version_id: int, update: CurriculumVersionLabelUpdate
) -> CurriculumVersionDetail:
    """Rename a curriculum version. Its status and its tree are unchanged."""
    CurriculumLibraryService(session).update_version_label(version_id, label=update.label)
    session.commit()
    return get_version(session, version_id)


@router.post("/versions/{version_id}/activate", response_model=CurriculumVersionDetail)
def activate_version(session: DbSession, version_id: int) -> CurriculumVersionDetail:
    """Make an already-approved curriculum version the live one again."""
    CurriculumLibraryService(session).activate(version_id)
    session.commit()
    return get_version(session, version_id)


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(session: DbSession, topic_id: int, update: CurriculumItemLabelUpdate) -> TopicOut:
    """Edit a topic's display name. Its stable id is untouched (ADR-021)."""
    topic = CurriculumLibraryService(session).update_topic(
        topic_id, name=update.name, description=update.description
    )
    session.commit()
    return TopicOut.from_row(topic)


@router.patch("/subtopics/{subtopic_id}", response_model=SubtopicSummary)
def update_subtopic(
    session: DbSession, subtopic_id: int, update: CurriculumItemLabelUpdate
) -> SubtopicSummary:
    """Edit a subtopic's display name.

    The stable id is not recomputed, so any weakness a student has been measured
    for on this skill stays attached to it (ADR-021).
    """
    subtopic = CurriculumLibraryService(session).update_subtopic(
        subtopic_id, name=update.name, description=update.description
    )
    session.commit()
    return SubtopicSummary.from_row(subtopic)


@router.delete("/versions/{version_id}", response_model=CurriculumVersionDeletion)
def delete_version(
    session: DbSession, version_id: int, force: bool = False
) -> CurriculumVersionDeletion:
    """Delete a curriculum version, its topics and its subtopics.

    Refuses with 409 while questions or students still name it, reporting every
    count. ``force`` proceeds anyway and the references are stranded. Two cases
    have no ``force`` path -- a frozen question set names the version, or it is
    the approved one -- because neither leaves a professor anything to decide.
    """
    repo = CurriculumRepository(session)
    topic_count = len(repo.topic_ids_in(version_id))
    subtopic_count = repo.subtopic_count(version_id)
    stranded = CurriculumLibraryService(session).delete(version_id, force=force)
    session.commit()
    return CurriculumVersionDeletion(
        deleted_version_id=version_id,
        deleted_topic_count=topic_count,
        deleted_subtopic_count=subtopic_count,
        stranded=CurriculumVersionUsage.from_usage(stranded),
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
