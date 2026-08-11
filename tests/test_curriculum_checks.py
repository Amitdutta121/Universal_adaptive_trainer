"""Deterministic structural checks on a proposed curriculum.

Each check corresponds to a downstream guarantee that would break silently:
grounding question generation in a Topic -> Subtopic pair, and tracking one
weakness dimension per subtopic. A proposal that fails any of them is discarded
whole rather than partly written.
"""

from __future__ import annotations

import pytest

from app.curriculum.checks import DefectCode, check_draft, require_sound_draft
from app.curriculum.draft import (
    CurriculumDraft,
    DraftEvidence,
    DraftSubtopic,
    DraftTopic,
    ExtractionMetadata,
    describe_topic,
)
from app.domain.books import SectionSource
from app.domain.enums import ConceptConfidence, StructureConfidence, StructureSource
from app.errors import CurriculumProposalError


def evidence(*, book_id: int = 1, section_id: int = 11) -> DraftEvidence:
    return DraftEvidence(
        candidate_label="Accessing characters",
        definition="Read one character by position.",
        quotes=["fruit[1]"],
        source=SectionSource(
            book_id=book_id,
            book_title="Think Python",
            section_id=section_id,
            chapter_number="8",
            chapter_title="Strings",
            section_number="8.1",
            section_title="Accessing Characters",
            start_page=85,
            end_page=86,
            structure_source=StructureSource.PDF_OUTLINE,
            structure_confidence=StructureConfidence.HIGH,
        ),
    )


def subtopic(
    *,
    stable_id: str = "sub-aaaaaaaaaaaa",
    topic_stable_id: str = "top-aaaaaaaaaaaa",
    name: str = "Indexing",
    with_evidence: bool = True,
) -> DraftSubtopic:
    return DraftSubtopic(
        stable_id=stable_id,
        topic_stable_id=topic_stable_id,
        name=name,
        description="Read one character from a string by position.",
        reason_for_grouping="Both teach retrieving characters by index.",
        confidence=ConceptConfidence.HIGH,
        candidate_labels=["Accessing characters"],
        evidence=[evidence()] if with_evidence else [],
    )


def topic(
    *,
    stable_id: str = "top-aaaaaaaaaaaa",
    name: str = "Strings",
    subtopics: list[DraftSubtopic] | None = None,
) -> DraftTopic:
    resolved = [subtopic()] if subtopics is None else subtopics
    return DraftTopic(
        stable_id=stable_id,
        name=name,
        description=describe_topic(name, resolved),
        subtopics=resolved,
    )


def draft(topics: list[DraftTopic]) -> CurriculumDraft:
    return CurriculumDraft(
        label="Test proposal",
        source_book_ids=[1],
        topics=topics,
        metadata=ExtractionMetadata(
            generated_by="scripted/test-model",
            stage_a_version="a/1",
            stage_b_version="b/1",
        ),
    )


def codes(candidate: CurriculumDraft) -> set[DefectCode]:
    return {defect.code for defect in check_draft(candidate)}


class TestSoundDrafts:
    def test_a_well_formed_draft_has_no_defects(self) -> None:
        assert check_draft(draft([topic()])) == []
        require_sound_draft(draft([topic()]))

    def test_a_topic_may_hold_several_subtopics(self) -> None:
        candidate = draft(
            [
                topic(
                    subtopics=[
                        subtopic(stable_id="sub-1", name="Indexing"),
                        subtopic(stable_id="sub-2", name="Slicing"),
                    ]
                )
            ]
        )
        assert check_draft(candidate) == []


class TestNameDefects:
    def test_a_blank_subtopic_name_is_a_defect(self) -> None:
        candidate = draft([topic(subtopics=[subtopic(name="   ")])])
        assert DefectCode.EMPTY_NAME in codes(candidate)

    def test_a_blank_topic_name_is_a_defect(self) -> None:
        assert DefectCode.EMPTY_NAME in codes(draft([topic(name="  ")]))

    def test_two_subtopics_of_one_name_are_a_defect(self) -> None:
        """One skill split across two weakness dimensions."""
        candidate = draft(
            [
                topic(
                    subtopics=[
                        subtopic(stable_id="sub-1", name="Indexing"),
                        subtopic(stable_id="sub-2", name="indexing"),
                    ]
                )
            ]
        )
        assert DefectCode.DUPLICATE_NAME in codes(candidate)

    def test_two_topics_of_one_name_are_a_defect(self) -> None:
        candidate = draft(
            [
                topic(stable_id="top-1", subtopics=[subtopic(topic_stable_id="top-1")]),
                topic(stable_id="top-2", subtopics=[subtopic(topic_stable_id="top-2")]),
            ]
        )
        assert DefectCode.DUPLICATE_NAME in codes(candidate)


class TestIdentityDefects:
    def test_a_duplicate_subtopic_id_is_a_defect(self) -> None:
        candidate = draft(
            [
                topic(
                    subtopics=[
                        subtopic(stable_id="sub-same", name="Indexing"),
                        subtopic(stable_id="sub-same", name="Slicing"),
                    ]
                )
            ]
        )
        assert DefectCode.DUPLICATE_STABLE_ID in codes(candidate)

    def test_a_duplicate_topic_id_is_a_defect(self) -> None:
        candidate = draft(
            [
                topic(stable_id="top-same", name="Strings"),
                topic(stable_id="top-same", name="Loops"),
            ]
        )
        assert DefectCode.DUPLICATE_STABLE_ID in codes(candidate)


class TestParentageDefects:
    def test_a_subtopic_claiming_another_parent_is_orphaned(self) -> None:
        candidate = draft([topic(stable_id="top-1", subtopics=[subtopic(topic_stable_id="top-9")])])
        assert DefectCode.ORPHANED_SUBTOPIC in codes(candidate)

    def test_a_topic_with_no_subtopics_is_a_defect(self) -> None:
        assert DefectCode.EMPTY_TOPIC in codes(draft([topic(subtopics=[])]))

    def test_a_proposal_with_no_topics_is_a_defect(self) -> None:
        assert DefectCode.NO_TOPICS in codes(draft([]))


class TestSourceMappingDefects:
    def test_a_subtopic_with_no_evidence_is_a_defect(self) -> None:
        """An ungrounded subtopic is the one thing proposal exists to avoid."""
        candidate = draft([topic(subtopics=[subtopic(with_evidence=False)])])
        assert DefectCode.MISSING_SOURCE_MAPPING in codes(candidate)

    def test_evidence_without_a_real_section_is_a_defect(self) -> None:
        broken = subtopic()
        broken.evidence = [evidence(section_id=0)]
        assert DefectCode.MISSING_SOURCE_MAPPING in codes(draft([topic(subtopics=[broken])]))


class TestFailureBehaviour:
    def test_every_defect_is_reported_not_just_the_first(self) -> None:
        candidate = draft(
            [
                topic(
                    name="  ",
                    subtopics=[subtopic(name="  ", with_evidence=False)],
                )
            ]
        )
        found = codes(candidate)
        assert DefectCode.EMPTY_NAME in found
        assert DefectCode.MISSING_SOURCE_MAPPING in found

    def test_an_unsound_draft_raises_and_names_the_problem(self) -> None:
        with pytest.raises(CurriculumProposalError) as caught:
            require_sound_draft(draft([topic(subtopics=[subtopic(with_evidence=False)])]))
        assert "missing_source_mapping" in (caught.value.detail or "")


class TestTopicDescription:
    def test_a_topic_description_lists_only_what_it_contains(self) -> None:
        """Derived, never generated: it cannot claim coverage that is not there."""
        described = describe_topic(
            "Strings",
            [subtopic(stable_id="s1", name="Indexing"), subtopic(stable_id="s2", name="Slicing")],
        )
        assert described == "Strings. Covers: Indexing, Slicing."

    def test_an_empty_topic_says_so(self) -> None:
        assert "No subtopics" in describe_topic("Strings", [])
