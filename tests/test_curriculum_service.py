"""The whole proposal workflow, from imported books to persisted rows.

Three real book documents are imported through the real ingestion service, then
the real pipeline runs over them with a scripted client standing in for the two
LLM stages. What is asserted is the milestone itself: after uploading several
books, a professor gets a Topic -> Subtopic hierarchy in which the same skill
described three different ways has become one subtopic, with its sources intact.
"""

from __future__ import annotations

import curriculum_fixtures as fixtures
import pytest
from sqlalchemy.orm import Session

from app.curriculum import CurriculumProposalService, decode_metadata, decode_proposal_warnings
from app.curriculum.draft import ProposalWarningCode
from app.domain.enums import ConceptConfidence, CurriculumItemStatus, CurriculumStatus
from app.errors import CurriculumProposalError, MalformedModelOutputError
from app.ingestion import BookImportService
from app.persistence.models import CurriculumVersionRow
from app.persistence.repositories import CurriculumRepository


@pytest.fixture
def three_books(session: Session, settings) -> Session:
    """Import the three fixture textbooks through the real ingestion path."""
    service = BookImportService(session, settings)
    for index, document in enumerate((fixtures.book_a(), fixtures.book_b(), fixtures.book_c())):
        service.import_upload(filename=f"book_{index}.json", data=fixtures.to_bytes(document))
    session.commit()
    return session


def propose(session: Session, settings, client=None) -> CurriculumVersionRow:
    service = CurriculumProposalService(
        session, client=client or fixtures.ScriptedClient(), settings=settings
    )
    version = service.propose()
    session.commit()
    return version


class TestTheMilestone:
    def test_three_books_yield_one_normalized_hierarchy(self, three_books, settings) -> None:
        version = propose(three_books, settings)

        assert version.status is CurriculumStatus.PROPOSED
        assert [topic.name for topic in version.topics] == ["Strings"]
        assert sorted(sub.name for sub in version.topics[0].subtopics) == [
            "Indexing",
            "Length",
            "Slicing",
        ]

    def test_the_same_skill_from_three_books_became_one_subtopic(
        self, three_books, settings
    ) -> None:
        version = propose(three_books, settings)
        indexing = next(sub for sub in version.topics[0].subtopics if sub.name == "Indexing")

        assert len(indexing.evidence) == 3
        assert len({item.book_id for item in indexing.evidence}) == 3
        assert sorted(item.candidate_label for item in indexing.evidence) == [
            "Accessing characters",
            "Selecting individual characters",
            "String indexing",
        ]

    def test_each_subtopic_cites_real_sections_of_real_books(self, three_books, settings) -> None:
        version = propose(three_books, settings)
        indexing = next(sub for sub in version.topics[0].subtopics if sub.name == "Indexing")

        citations = sorted(item.citation for item in indexing.evidence)
        assert "Think Python" in citations[2]
        for item in indexing.evidence:
            # Each evidence row points at a section that actually exists.
            assert item.section.book_id == item.book_id
            assert item.section.text

    def test_the_grouping_rationale_is_stored(self, three_books, settings) -> None:
        version = propose(three_books, settings)
        indexing = next(sub for sub in version.topics[0].subtopics if sub.name == "Indexing")
        assert "retrieving individual characters" in (indexing.grouping_reason or "")

    def test_nothing_is_approved_automatically(self, three_books, settings) -> None:
        """Proposing and approving stay separate; ADR-002 still gates generation."""
        version = propose(three_books, settings)

        assert version.status is CurriculumStatus.PROPOSED
        assert all(topic.review_status is CurriculumItemStatus.PROPOSED for topic in version.topics)
        assert all(
            sub.review_status is CurriculumItemStatus.PROPOSED
            for topic in version.topics
            for sub in topic.subtopics
        )
        assert CurriculumRepository(three_books).get_approved() is None


class TestTraceabilityAndProvenance:
    def test_stable_ids_are_written_for_every_item(self, three_books, settings) -> None:
        version = propose(three_books, settings)
        for topic in version.topics:
            assert topic.stable_id and topic.stable_id.startswith("top-")
            for subtopic in topic.subtopics:
                assert subtopic.stable_id and subtopic.stable_id.startswith("sub-")

    def test_re_running_the_proposal_reproduces_the_same_ids(self, three_books, settings) -> None:
        """Identity is a function of the source material, so a re-run agrees."""
        first = propose(three_books, settings)
        first_ids = sorted(sub.stable_id for topic in first.topics for sub in topic.subtopics)

        second = propose(three_books, settings)
        second_ids = sorted(sub.stable_id for topic in second.topics for sub in topic.subtopics)

        assert first.id != second.id
        assert first_ids == second_ids

    def test_the_model_and_stage_versions_are_recorded(self, three_books, settings) -> None:
        version = propose(three_books, settings)

        assert version.generated_by == "scripted/test-model"
        metadata = decode_metadata(version.extraction_metadata_json)
        assert metadata is not None
        assert metadata.books_analysed == 3
        assert metadata.stage_a_version == "section-analysis/1"
        assert metadata.stage_b_version == "cross-book-normalization/1"

    def test_the_source_books_are_recorded(self, three_books, settings) -> None:
        version = propose(three_books, settings)
        from app.curriculum import decode_json_list

        assert len(decode_json_list(version.source_book_ids_json)) == 3

    def test_confidence_is_carried_through_to_storage(self, three_books, settings) -> None:
        version = propose(three_books, settings)
        slicing = next(sub for sub in version.topics[0].subtopics if sub.name == "Slicing")
        assert slicing.confidence is ConceptConfidence.HIGH


class TestNonInstructionalContent:
    def test_front_matter_contributes_no_subtopic(self, three_books, settings) -> None:
        """ "About This Book" is analysed, found non-instructional, and dropped."""
        client = fixtures.ScriptedClient()
        version = propose(three_books, settings, client=client)

        analysed = [prompt for name, prompt in client.prompts if name == "record_section_analysis"]
        assert any("About This Book" in prompt for prompt in analysed)

        labels = {
            item.candidate_label
            for topic in version.topics
            for sub in topic.subtopics
            for item in sub.evidence
        }
        assert not any("About This Book" in label for label in labels)


class TestBoundedAndReportedRuns:
    def test_the_section_limit_is_honoured_and_declared(
        self, three_books, settings, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "curriculum_max_sections", 2)
        version = propose(three_books, settings)

        warnings = decode_proposal_warnings(version.warnings_json)
        assert ProposalWarningCode.SECTIONS_SKIPPED in [w.code for w in warnings]
        metadata = decode_metadata(version.extraction_metadata_json)
        assert metadata is not None
        assert metadata.sections_analysed <= 2

    def test_truncated_sections_are_declared(self, three_books, settings, monkeypatch) -> None:
        monkeypatch.setattr(settings, "curriculum_section_char_budget", 20)
        version = propose(three_books, settings)

        warnings = decode_proposal_warnings(version.warnings_json)
        assert ProposalWarningCode.SECTION_TEXT_TRUNCATED in [w.code for w in warnings]

    def test_a_candidate_the_model_forgot_is_declared(self, three_books, settings) -> None:
        client = fixtures.ScriptedClient(drop_candidate_ids=("c002",))
        version = propose(three_books, settings, client=client)

        warnings = decode_proposal_warnings(version.warnings_json)
        assert ProposalWarningCode.CANDIDATES_UNASSIGNED in [w.code for w in warnings]

    def test_one_failed_section_does_not_lose_the_whole_run(self, three_books, settings) -> None:
        """A single bad response should not cost an entire textbook's analysis."""

        class OneBadSection(fixtures.ScriptedClient):
            def _analyse(self, prompt: str) -> dict:
                if "String Indexing" in prompt:
                    return {"teaches": "", "is_instructional": "maybe"}
                return super()._analyse(prompt)

        version = propose(three_books, settings, client=OneBadSection())

        warnings = decode_proposal_warnings(version.warnings_json)
        assert ProposalWarningCode.SECTION_ANALYSIS_FAILED in [w.code for w in warnings]
        # The rest of the books still produced a usable hierarchy.
        assert version.topics


class TestRefusals:
    def test_proposing_without_books_is_refused(self, session, settings) -> None:
        service = CurriculumProposalService(
            session, client=fixtures.ScriptedClient(), settings=settings
        )
        with pytest.raises(CurriculumProposalError) as caught:
            service.propose()
        assert "no imported books" in caught.value.message.lower()

    def test_a_run_that_finds_no_concepts_is_refused(self, three_books, settings) -> None:
        """No empty curriculum is written: the run fails and says so."""
        silent = fixtures.ScriptedClient(
            stage_a_override={
                "teaches": "Nothing assessable here.",
                "is_instructional": False,
                "concepts": [],
                "confidence": "high",
            }
        )
        with pytest.raises(CurriculumProposalError):
            propose(three_books, settings, client=silent)

    def test_a_malformed_normalization_response_fails_the_run(self, three_books, settings) -> None:
        broken = fixtures.ScriptedClient(stage_b_override={"groups": "everything"})
        with pytest.raises(MalformedModelOutputError):
            propose(three_books, settings, client=broken)

    def test_a_failed_run_writes_no_curriculum(self, three_books, settings) -> None:
        broken = fixtures.ScriptedClient(stage_b_override={"groups": []})
        with pytest.raises(MalformedModelOutputError):
            propose(three_books, settings, client=broken)
        three_books.rollback()
        assert CurriculumRepository(three_books).count() == 0
