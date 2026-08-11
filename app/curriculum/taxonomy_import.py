"""Import a professor-uploaded fixed taxonomy as an APPROVED curriculum version."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.curriculum.taxonomy_ids import subtopic_id_from_names, topic_id_from_name
from app.curriculum.taxonomy_schema import TaxonomyDocument, parse_taxonomy_document
from app.domain.enums import CurriculumItemStatus, CurriculumStatus
from app.errors import UnsupportedFileError
from app.persistence.models import CurriculumVersionRow, SubtopicRow, TopicRow
from app.persistence.repositories import CurriculumRepository

logger = logging.getLogger(__name__)

GENERATED_BY = "taxonomy-upload"


class TaxonomyImportService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._curriculum = CurriculumRepository(session)

    def import_upload(self, *, filename: str, data: bytes) -> CurriculumVersionRow:
        if not filename.lower().endswith(".json"):
            raise UnsupportedFileError(
                "Only .json taxonomy documents are accepted.",
                detail=f"Got {filename!r}.",
            )
        # Reuse book size limit — taxonomies are tiny; keeps one knob.
        max_bytes = self._settings.max_book_upload_mb * 1024 * 1024
        if len(data) > max_bytes:
            from app.errors import FileTooLargeError

            raise FileTooLargeError(
                "The taxonomy file is too large.",
                detail=f"{len(data)} bytes exceeds the configured limit.",
            )

        document = parse_taxonomy_document(data)
        version = self._persist(document)
        logger.info(
            "Imported taxonomy version %s (%d topic(s))",
            version.id,
            len(version.topics),
        )
        return version

    def _persist(self, document: TaxonomyDocument) -> CurriculumVersionRow:
        now = datetime.now(UTC)
        version = self._curriculum.add(
            CurriculumVersionRow(
                label=document.label,
                status=CurriculumStatus.APPROVED,
                approved_at=now,
                generated_by=GENERATED_BY,
                source_book_ids=[],
                extraction_metadata=None,
                warnings=[],
            )
        )
        for position, topic in enumerate(document.topics):
            topic_row = TopicRow(
                name=topic.name,
                description=topic.description or None,
                position=position,
                stable_id=topic_id_from_name(topic.name),
                review_status=CurriculumItemStatus.ACCEPTED,
            )
            for sub_position, subtopic in enumerate(topic.subtopics):
                topic_row.subtopics.append(
                    SubtopicRow(
                        name=subtopic.name,
                        description=subtopic.description or None,
                        position=sub_position,
                        stable_id=subtopic_id_from_names(topic.name, subtopic.name),
                        review_status=CurriculumItemStatus.ACCEPTED,
                        candidate_labels=[],
                        grouping_reason=None,
                        confidence=None,
                    )
                )
            version.topics.append(topic_row)
        self._session.flush()
        return version
