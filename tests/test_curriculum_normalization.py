"""Stage B: consolidating candidates across books, and the bookkeeping around it.

The model's judgement about *equivalence* is faked here. What is under test is
everything deterministic that surrounds it: that the answer is checked against
the question, that nothing is dropped in silence, that identity survives a
rename, and that sources are preserved all the way through.
"""

from __future__ import annotations

import pytest

from app.curriculum.candidates import SectionCandidate
from app.curriculum.draft import ExtractionMetadata, ProposalWarningCode
from app.curriculum.normalization import (
    assemble_draft,
    build_normalization_prompt,
)
from app.curriculum.schema import CandidateConcept, NormalizationResult, parse_structured
from app.curriculum.stable_ids import normalize_label, subtopic_stable_id
from app.domain.books import SectionSource
from app.domain.enums import ConceptConfidence, StructureConfidence, StructureSource
from app.errors import MalformedModelOutputError


def source(
    *,
    book_id: int,
    book_title: str,
    section_id: int,
    number: str,
    title: str,
    chapter: str = "8",
) -> SectionSource:
    return SectionSource(
        book_id=book_id,
        book_title=book_title,
        section_id=section_id,
        chapter_id=book_id * 10,
        chapter_number=chapter,
        chapter_title="Strings",
        section_number=number,
        section_title=title,
        start_page=10 + section_id,
        end_page=11 + section_id,
        structure_source=StructureSource.PDF_OUTLINE,
        structure_confidence=StructureConfidence.HIGH,
    )


def candidate(
    candidate_id: str,
    *,
    label: str,
    book_id: int,
    book_title: str,
    section_id: int,
    number: str,
    title: str,
    topic_label: str = "Strings",
) -> SectionCandidate:
    return SectionCandidate(
        candidate_id=candidate_id,
        concept=CandidateConcept(
            label=label,
            topic_label=topic_label,
            definition=f"What {label.lower()} lets a student do.",
            evidence=[f"example for {label}"],
            confidence=ConceptConfidence.HIGH,
        ),
        source=source(
            book_id=book_id,
            book_title=book_title,
            section_id=section_id,
            number=number,
            title=title,
        ),
        section_teaches=f"This section teaches {label.lower()}.",
    )


#: The motivating case: three books, three wordings, one skill.
THREE_BOOKS = [
    candidate(
        "c001",
        label="Accessing characters",
        book_id=1,
        book_title="Think Python",
        section_id=11,
        number="8.1",
        title="Accessing Characters",
    ),
    candidate(
        "c002",
        label="String indexing",
        book_id=2,
        book_title="Python Crash Course",
        section_id=21,
        number="2.3",
        title="String Indexing",
    ),
    candidate(
        "c003",
        label="Selecting individual characters",
        book_id=3,
        book_title="Automate the Boring Stuff",
        section_id=31,
        number="6.1",
        title="Selecting Individual Characters",
    ),
]


def group(
    *,
    topic: str = "Strings",
    subtopic: str = "Indexing",
    ids: list[str],
    reason: str = "All three teach retrieving individual characters using indices.",
    confidence: str = "high",
) -> dict:
    return {
        "normalized_topic": topic,
        "normalized_subtopic": subtopic,
        "normalized_description": "Read one character from a string by position.",
        "reason_for_grouping": reason,
        "confidence": confidence,
        "candidate_ids": ids,
    }


def result_from(*groups: dict) -> NormalizationResult:
    return parse_structured(NormalizationResult, {"groups": list(groups)}, stage="normalization")


def metadata() -> ExtractionMetadata:
    return ExtractionMetadata(
        generated_by="scripted/test-model",
        stage_a_version="section-analysis/1",
        stage_b_version="cross-book-normalization/1",
    )


def build(candidates, result, **kwargs):
    return assemble_draft(
        candidates,
        result,
        label=kwargs.pop("label", "Test proposal"),
        source_book_ids=kwargs.pop("source_book_ids", [1, 2, 3]),
        metadata=metadata(),
        **kwargs,
    )


class TestCrossBookGrouping:
    def test_three_wordings_become_one_subtopic(self) -> None:
        draft = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))

        assert [topic.name for topic in draft.topics] == ["Strings"]
        subtopic = draft.topics[0].subtopics[0]
        assert subtopic.name == "Indexing"
        assert subtopic.section_count == 3
        assert subtopic.book_count == 3
        assert subtopic.is_cross_book is True
        assert draft.cross_book_subtopic_count == 1

    def test_the_merged_wordings_are_retained(self) -> None:
        """A professor reviewing a merge must see what was merged."""
        draft = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        assert draft.topics[0].subtopics[0].candidate_labels == [
            "Accessing characters",
            "String indexing",
            "Selecting individual characters",
        ]

    def test_the_reason_for_grouping_is_retained(self) -> None:
        draft = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        assert "retrieving individual characters" in (
            draft.topics[0].subtopics[0].reason_for_grouping
        )

    def test_every_source_section_is_preserved(self) -> None:
        draft = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        subtopic = draft.topics[0].subtopics[0]

        assert subtopic.section_ids == [11, 21, 31]
        assert subtopic.book_ids == [1, 2, 3]
        assert [item.candidate_label for item in subtopic.evidence] == [
            "Accessing characters",
            "String indexing",
            "Selecting individual characters",
        ]
        assert [item.quotes for item in subtopic.evidence] == [
            ["example for Accessing characters"],
            ["example for String indexing"],
            ["example for Selecting individual characters"],
        ]

    def test_evidence_can_cite_its_section(self) -> None:
        draft = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        citation = draft.topics[0].subtopics[0].evidence[0].citation
        assert "Think Python" in citation
        assert "8.1 Accessing Characters" in citation

    def test_a_single_candidate_may_stand_alone(self) -> None:
        draft = build(
            THREE_BOOKS,
            result_from(
                group(ids=["c001", "c002"]),
                group(subtopic="Slicing", ids=["c003"], reason="Teaches substrings."),
            ),
        )
        names = {sub.name: sub for sub in draft.topics[0].subtopics}
        assert names["Slicing"].section_count == 1
        assert names["Slicing"].is_cross_book is False

    def test_subtopics_are_ordered_by_support_then_name(self) -> None:
        """Deterministic ordering: best-supported skills reviewed first."""
        draft = build(
            THREE_BOOKS,
            result_from(
                group(subtopic="Slicing", ids=["c003"]),
                group(subtopic="Indexing", ids=["c001", "c002"]),
            ),
        )
        assert [sub.name for sub in draft.topics[0].subtopics] == ["Indexing", "Slicing"]
        assert [sub.position for sub in draft.topics[0].subtopics] == [0, 1]

    def test_topics_group_separately(self) -> None:
        candidates = [
            *THREE_BOOKS[:1],
            candidate(
                "c002",
                label="While loops",
                topic_label="Loops",
                book_id=2,
                book_title="Python Crash Course",
                section_id=22,
                number="7.1",
                title="While Loops",
            ),
        ]
        draft = build(
            candidates,
            result_from(
                group(ids=["c001"]),
                group(topic="Loops", subtopic="While loops", ids=["c002"]),
            ),
        )
        assert sorted(topic.name for topic in draft.topics) == ["Loops", "Strings"]


class TestMisreferencingResponses:
    """An answer that does not refer to the question is not repaired."""

    def test_an_invented_candidate_id_is_rejected(self) -> None:
        with pytest.raises(MalformedModelOutputError) as caught:
            build(THREE_BOOKS, result_from(group(ids=["c001", "c999"])))
        assert "c999" in (caught.value.detail or "")

    def test_a_candidate_placed_in_two_groups_is_rejected(self) -> None:
        with pytest.raises(MalformedModelOutputError) as caught:
            build(
                THREE_BOOKS,
                result_from(
                    group(ids=["c001", "c002"]),
                    group(subtopic="Slicing", ids=["c002", "c003"]),
                ),
            )
        assert "c002" in (caught.value.detail or "")

    def test_a_candidate_repeated_inside_one_group_is_rejected(self) -> None:
        with pytest.raises(MalformedModelOutputError):
            build(THREE_BOOKS, result_from(group(ids=["c001", "c001"])))


class TestLosslessness:
    def test_an_unassigned_candidate_is_reported_not_hidden(self) -> None:
        draft = build(THREE_BOOKS, result_from(group(ids=["c001", "c002"])))

        codes = [warning.code for warning in draft.warnings]
        assert ProposalWarningCode.CANDIDATES_UNASSIGNED in codes
        warning = next(
            w for w in draft.warnings if w.code == ProposalWarningCode.CANDIDATES_UNASSIGNED
        )
        assert "1 candidate concept(s)" in warning.message
        assert "Selecting individual characters" in (warning.location or "")

    def test_nothing_is_reported_when_everything_was_placed(self) -> None:
        draft = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        assert draft.warnings == []


class TestDuplicateGroups:
    def test_two_groups_with_the_same_name_are_merged(self) -> None:
        """Two subtopics of one name would split one weakness dimension in half."""
        draft = build(
            THREE_BOOKS,
            result_from(
                group(ids=["c001"], reason="Teaches character access."),
                group(ids=["c002", "c003"], reason="Teaches indexing."),
            ),
        )

        assert len(draft.topics[0].subtopics) == 1
        subtopic = draft.topics[0].subtopics[0]
        assert subtopic.section_count == 3
        assert "Teaches character access" in subtopic.reason_for_grouping
        assert "Teaches indexing" in subtopic.reason_for_grouping

    def test_the_merge_is_reported(self) -> None:
        draft = build(
            THREE_BOOKS,
            result_from(group(ids=["c001"]), group(ids=["c002", "c003"])),
        )
        assert ProposalWarningCode.DUPLICATE_GROUPS_MERGED in [w.code for w in draft.warnings]

    def test_differently_spelled_duplicates_still_merge(self) -> None:
        draft = build(
            THREE_BOOKS,
            result_from(
                group(subtopic="Indexing", ids=["c001"]),
                group(subtopic="  indexing  ", ids=["c002", "c003"]),
            ),
        )
        assert len(draft.topics[0].subtopics) == 1

    def test_a_merge_takes_the_more_cautious_confidence(self) -> None:
        draft = build(
            THREE_BOOKS,
            result_from(
                group(ids=["c001"], confidence="high"),
                group(ids=["c002", "c003"], confidence="low"),
            ),
        )
        assert draft.topics[0].subtopics[0].confidence is ConceptConfidence.LOW


class TestStableIds:
    def test_the_same_input_always_yields_the_same_ids(self) -> None:
        first = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        second = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        assert first.topics[0].stable_id == second.topics[0].stable_id
        assert first.subtopics[0].stable_id == second.subtopics[0].stable_id

    def test_renaming_the_subtopic_does_not_change_its_id(self) -> None:
        """The point of the scheme: a professor's rename must not break identity."""
        original = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        renamed = build(
            THREE_BOOKS,
            result_from(
                group(
                    subtopic="Reading characters by position",
                    ids=["c001", "c002", "c003"],
                )
            ),
        )
        assert renamed.subtopics[0].name != original.subtopics[0].name
        assert renamed.subtopics[0].stable_id == original.subtopics[0].stable_id

    def test_renaming_the_topic_does_not_change_either_id(self) -> None:
        original = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        renamed = build(
            THREE_BOOKS,
            result_from(group(topic="Text and strings", ids=["c001", "c002", "c003"])),
        )
        assert renamed.topics[0].name == "Text and strings"
        assert renamed.topics[0].stable_id == original.topics[0].stable_id
        assert renamed.subtopics[0].stable_id == original.subtopics[0].stable_id

    def test_a_different_grouping_gets_a_different_id(self) -> None:
        whole = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        partial = build(THREE_BOOKS, result_from(group(ids=["c001", "c002"])))
        assert whole.subtopics[0].stable_id != partial.subtopics[0].stable_id

    def test_ids_are_prefixed_and_distinguishable(self) -> None:
        draft = build(THREE_BOOKS, result_from(group(ids=["c001", "c002", "c003"])))
        assert draft.topics[0].stable_id.startswith("top-")
        assert draft.subtopics[0].stable_id.startswith("sub-")
        assert draft.subtopics[0].topic_stable_id == draft.topics[0].stable_id

    def test_label_normalisation_ignores_case_and_punctuation(self) -> None:
        assert normalize_label("Accessing Characters!") == "accessing characters"
        assert normalize_label("accessing-characters") == "accessing characters"
        assert normalize_label("  ACCESSING   characters  ") == "accessing characters"

    def test_identity_survives_a_reordering_of_its_parts(self) -> None:
        forward = subtopic_stable_id(
            candidate_labels=["A", "B"],
            candidate_topic_labels=["Strings"],
            source_keys=["k1", "k2"],
        )
        backward = subtopic_stable_id(
            candidate_labels=["B", "A"],
            candidate_topic_labels=["Strings"],
            source_keys=["k2", "k1"],
        )
        assert forward == backward


class TestNormalizationPrompt:
    def test_every_candidate_is_addressable_in_the_prompt(self) -> None:
        prompt = build_normalization_prompt(THREE_BOOKS)
        for item in THREE_BOOKS:
            assert item.candidate_id in prompt
            assert item.concept.label in prompt
            assert item.source.book_title in prompt

    def test_the_prompt_states_how_many_must_be_grouped(self) -> None:
        assert "Group all 3 candidate(s)" in build_normalization_prompt(THREE_BOOKS)
