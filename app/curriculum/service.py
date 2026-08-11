"""The curriculum proposal workflow: analyse, normalise, check, store.

One entry point, :meth:`CurriculumProposalService.propose`. It reads the sections
of the professor's imported books, runs Stage A over each, runs Stage B over
everything the two stages found, checks the result, and writes a ``PROPOSED``
curriculum version.

Order matters, and it is the same order ingestion uses (ADR-015): the whole
proposal is assembled and checked in memory, and only then is anything written.
A run that fails leaves no half-built curriculum behind.

What this stage does not do
    It does not approve anything. The version it writes is ``PROPOSED``, every
    topic and subtopic is ``PROPOSED``, and question generation still requires an
    approved version (ADR-002). Proposing and approving stay separate because the
    professor's approval is the whole point of the review step.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.curriculum.candidates import AnalysedSection, build_candidates
from app.curriculum.checks import require_sound_draft
from app.curriculum.draft import (
    CurriculumDraft,
    DraftSubtopic,
    DraftTopic,
    ExtractionMetadata,
    ProposalWarning,
    ProposalWarningCode,
)
from app.curriculum.extraction import SectionConceptExtractor
from app.curriculum.normalization import CrossBookNormalizer, assemble_draft
from app.curriculum.schema import STAGE_A_VERSION, STAGE_B_VERSION
from app.domain.books import BookSection, SectionSource
from app.domain.enums import CurriculumStatus
from app.errors import CurriculumProposalError, MalformedModelOutputError
from app.ingestion.retrieval import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import (
    BookRow,
    CurriculumVersionRow,
    SubtopicEvidenceRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import BookRepository, CurriculumRepository

logger = logging.getLogger(__name__)


class CurriculumProposalService:
    """Derives a proposed Topic -> Subtopic curriculum from imported books."""

    def __init__(
        self,
        session: Session,
        client: StructuredLLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        # Resolved eagerly so an unconfigured run fails before any work is done,
        # rather than after analysing half a textbook.
        self._client = client or get_structured_client(self._settings)
        self._books = BookRepository(session)
        self._curriculum = CurriculumRepository(session)
        self._retrieval = SourceRetrieval(session)
        self._extractor = SectionConceptExtractor(self._client, self._settings)
        self._normalizer = CrossBookNormalizer(self._client, self._settings)

    def propose(self, book_ids: Sequence[int] | None = None) -> CurriculumVersionRow:
        """Propose a curriculum from the given books, or from every usable book.

        Returns:
            The persisted ``PROPOSED`` curriculum version, with its topics,
            subtopics and evidence written.

        Raises:
            CurriculumProposalError: no usable books, no analysable sections, no
                concepts found, or the proposal failed a structural check.
            ConfigurationError: no LLM provider or credentials are configured.
            LLMRequestError: the provider could not be reached.
            MalformedModelOutputError: a stage returned unusable output.
        """
        books = self._resolve_books(book_ids)
        sections = self._collect_sections(books)
        analysed, warnings = self._run_stage_a(sections)

        candidates = build_candidates(analysed)
        if not candidates:
            raise CurriculumProposalError(
                "No assessable concepts were found in the selected books.",
                detail=(
                    f"{len(analysed)} section(s) were analysed but none yielded a concept "
                    "that could be practised and assessed."
                ),
            )

        result = self._normalizer.normalize(candidates)
        draft = assemble_draft(
            candidates,
            result,
            label=self._build_label(len(books)),
            source_book_ids=[book.id for book in books],
            metadata=ExtractionMetadata(
                generated_by=self._client.description,
                stage_a_version=STAGE_A_VERSION,
                stage_b_version=STAGE_B_VERSION,
                books_analysed=len(books),
                sections_analysed=len(analysed),
                sections_skipped=len(sections) - len(analysed),
                candidates_extracted=len(candidates),
                groups_returned=len(result.groups),
            ),
            warnings=warnings,
        )
        require_sound_draft(draft)

        version = self._persist(draft)
        logger.info(
            "Proposed curriculum version %s: %d topic(s), %d subtopic(s) from %d book(s)",
            version.id,
            len(draft.topics),
            draft.subtopic_count,
            len(books),
        )
        return version

    # -- steps -------------------------------------------------------------

    def _resolve_books(self, book_ids: Sequence[int] | None) -> list[BookRow]:
        """The books to ground this proposal in."""
        if book_ids:
            books = [self._books.get(book_id) for book_id in book_ids]
        else:
            books = self._books.list_usable()
        if not books:
            raise CurriculumProposalError(
                "There are no imported books to derive a curriculum from.",
                detail="Upload at least one book document on the Books page first.",
            )
        return books

    def _collect_sections(
        self, books: Sequence[BookRow]
    ) -> list[tuple[BookSection, SectionSource]]:
        """Every non-empty section of every selected book, in reading order."""
        collected: list[tuple[BookSection, SectionSource]] = []
        for book in books:
            for section in self._retrieval.sections_in_book(book.id):
                if section.is_empty or section.id is None:
                    continue
                collected.append((section, self._retrieval.section_source(section.id)))
        if not collected:
            raise CurriculumProposalError(
                "The selected books contain no section text to analyse.",
                detail=f"{len(books)} book(s) were selected.",
            )
        return collected

    def _run_stage_a(
        self, sections: Sequence[tuple[BookSection, SectionSource]]
    ) -> tuple[list[AnalysedSection], list[ProposalWarning]]:
        """Analyse each section, bounded by the configured section limit.

        A section whose analysis fails does not abort the run -- one bad section
        out of two hundred should not cost the whole proposal -- but every
        failure and every skip is recorded as a warning on the result.
        """
        limit = self._settings.curriculum_max_sections
        warnings: list[ProposalWarning] = []
        analysed: list[AnalysedSection] = []
        truncated_count = 0

        if len(sections) > limit:
            warnings.append(
                ProposalWarning(
                    code=ProposalWarningCode.SECTIONS_SKIPPED,
                    message=(
                        f"Only the first {limit} of {len(sections)} sections were analysed "
                        "(CURRICULUM_MAX_SECTIONS). The proposal does not cover the rest."
                    ),
                )
            )

        for section, source in sections[:limit]:
            try:
                analysis, truncated = self._extractor.analyse(section, source)
            except MalformedModelOutputError as exc:
                logger.warning("Stage A failed for section %s: %s", source.section_id, exc.message)
                warnings.append(
                    ProposalWarning(
                        code=ProposalWarningCode.SECTION_ANALYSIS_FAILED,
                        message=f"Section analysis failed: {exc.message}",
                        location=source.citation(),
                    )
                )
                continue
            truncated_count += 1 if truncated else 0
            if analysis.is_instructional and analysis.concepts:
                analysed.append(AnalysedSection(source=source, analysis=analysis))

        if truncated_count:
            warnings.append(
                ProposalWarning(
                    code=ProposalWarningCode.SECTION_TEXT_TRUNCATED,
                    message=(
                        f"{truncated_count} section(s) were longer than the analysis context "
                        "budget and were truncated for analysis. The stored sections are "
                        "unchanged."
                    ),
                )
            )
        return analysed, warnings

    def _build_label(self, book_count: int) -> str:
        """A human-readable, unambiguous name for this proposal."""
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        return f"Proposed from {book_count} book(s) — {stamp}"

    # -- persistence -------------------------------------------------------

    def _persist(self, draft: CurriculumDraft) -> CurriculumVersionRow:
        """Write the checked draft as a PROPOSED version. Nothing is approved."""
        version = self._curriculum.add(
            CurriculumVersionRow(
                label=draft.label,
                status=CurriculumStatus.PROPOSED,
                source_book_ids_json=json.dumps(draft.source_book_ids),
                generated_by=draft.metadata.generated_by,
                extraction_metadata_json=draft.metadata.model_dump_json(),
                warnings_json=json.dumps(
                    [warning.model_dump(mode="json") for warning in draft.warnings]
                )
                if draft.warnings
                else None,
            )
        )
        for topic in draft.topics:
            version.topics.append(_topic_row(topic))
        self._session.flush()
        return version


def _topic_row(topic: DraftTopic) -> TopicRow:
    row = TopicRow(
        name=topic.name,
        description=topic.description,
        position=topic.position,
        stable_id=topic.stable_id,
    )
    row.subtopics.extend(_subtopic_row(subtopic) for subtopic in topic.subtopics)
    return row


def _subtopic_row(subtopic: DraftSubtopic) -> SubtopicRow:
    row = SubtopicRow(
        name=subtopic.name,
        description=subtopic.description,
        position=subtopic.position,
        stable_id=subtopic.stable_id,
        candidate_labels_json=json.dumps(subtopic.candidate_labels),
        grouping_reason=subtopic.reason_for_grouping,
        confidence=subtopic.confidence,
    )
    row.evidence.extend(
        SubtopicEvidenceRow(
            book_id=evidence.source.book_id,
            section_id=evidence.source.section_id,
            candidate_label=evidence.candidate_label,
            definition=evidence.definition,
            quotes_json=json.dumps(evidence.quotes) if evidence.quotes else None,
            citation=evidence.citation,
            position=position,
        )
        for position, evidence in enumerate(subtopic.evidence)
    )
    return row


def decode_json_list(raw: str | None) -> list:
    """Read a JSON list column back, tolerating a row written by an older format.

    Used for candidate labels, evidence quotes and source book ids. Returns an
    empty list rather than raising: a display-only field must not take a page
    down.
    """
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Discarding unreadable JSON list payload")
        return []
    return payload if isinstance(payload, list) else []


def decode_proposal_warnings(raw: str | None) -> list[ProposalWarning]:
    """Read a version's declared caveats back for display."""
    warnings: list[ProposalWarning] = []
    for item in decode_json_list(raw):
        try:
            warnings.append(ProposalWarning.model_validate(item))
        except ValueError:
            continue
    return warnings


def decode_metadata(raw: str | None) -> ExtractionMetadata | None:
    """Read a version's extraction metadata back, or ``None`` if unreadable."""
    if not raw:
        return None
    try:
        return ExtractionMetadata.model_validate_json(raw)
    except ValueError:
        logger.warning("Discarding unreadable extraction metadata")
        return None
