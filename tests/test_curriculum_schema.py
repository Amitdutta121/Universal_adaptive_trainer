"""The structured contract with the model, in both directions.

Strictness is the point: a response that does not satisfy the schema is rejected
rather than repaired, because a partially understood analysis would put invented
curriculum structure in front of the professor.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.curriculum.schema import (
    MAX_CONCEPTS_PER_SECTION,
    ConceptGroup,
    NormalizationResult,
    SectionAnalysis,
    json_schema_for,
    parse_structured,
)
from app.domain.enums import ConceptConfidence
from app.errors import MalformedModelOutputError


def valid_concept(**overrides: Any) -> dict[str, Any]:
    concept = {
        "label": "String indexing",
        "topic_label": "Strings",
        "definition": "Retrieve a character from a string using an index.",
        "evidence": ["message[0]"],
        "confidence": "high",
    }
    concept.update(overrides)
    return concept


def valid_analysis(**overrides: Any) -> dict[str, Any]:
    analysis = {
        "teaches": "How to read a character out of a string.",
        "is_instructional": True,
        "concepts": [valid_concept()],
        "confidence": "high",
    }
    analysis.update(overrides)
    return analysis


class TestSectionAnalysis:
    def test_a_well_formed_analysis_parses(self) -> None:
        analysis = parse_structured(SectionAnalysis, valid_analysis(), stage="section analysis")
        assert analysis.is_instructional is True
        assert analysis.concepts[0].label == "String indexing"
        assert analysis.concepts[0].confidence is ConceptConfidence.HIGH

    def test_an_invented_field_is_rejected(self) -> None:
        """``extra="forbid"``: a key the model made up is an error, not noise."""
        with pytest.raises(MalformedModelOutputError) as caught:
            parse_structured(
                SectionAnalysis,
                valid_analysis(difficulty="easy"),
                stage="section analysis",
            )
        assert "difficulty" in (caught.value.detail or "")

    @pytest.mark.parametrize("missing", ["teaches", "is_instructional", "confidence"])
    def test_missing_required_fields_are_rejected(self, missing: str) -> None:
        payload = valid_analysis()
        payload.pop(missing)
        with pytest.raises(MalformedModelOutputError):
            parse_structured(SectionAnalysis, payload, stage="section analysis")

    def test_a_concept_without_evidence_is_rejected(self) -> None:
        """A concept with no support in the text is an unverifiable assertion."""
        with pytest.raises(MalformedModelOutputError):
            parse_structured(
                SectionAnalysis,
                valid_analysis(concepts=[valid_concept(evidence=[])]),
                stage="section analysis",
            )

    def test_a_blank_label_is_rejected(self) -> None:
        with pytest.raises(MalformedModelOutputError):
            parse_structured(
                SectionAnalysis,
                valid_analysis(concepts=[valid_concept(label="   ")]),
                stage="section analysis",
            )

    def test_non_instructional_sections_may_not_propose_concepts(self) -> None:
        """The contradiction is refused rather than silently half-believed."""
        with pytest.raises(MalformedModelOutputError) as caught:
            parse_structured(
                SectionAnalysis,
                valid_analysis(is_instructional=False),
                stage="section analysis",
            )
        assert "is_instructional" in (caught.value.detail or "")

    def test_a_non_instructional_section_with_no_concepts_is_fine(self) -> None:
        analysis = parse_structured(
            SectionAnalysis,
            valid_analysis(is_instructional=False, concepts=[]),
            stage="section analysis",
        )
        assert analysis.concepts == []

    def test_too_many_concepts_are_rejected(self) -> None:
        """The guard against splitting one section into a glossary of micro-terms."""
        payload = valid_analysis(
            concepts=[
                valid_concept(label=f"Concept {index}")
                for index in range(MAX_CONCEPTS_PER_SECTION + 1)
            ]
        )
        with pytest.raises(MalformedModelOutputError):
            parse_structured(SectionAnalysis, payload, stage="section analysis")

    def test_an_unknown_confidence_value_is_rejected(self) -> None:
        with pytest.raises(MalformedModelOutputError):
            parse_structured(
                SectionAnalysis, valid_analysis(confidence="very sure"), stage="section analysis"
            )


class TestNormalizationResult:
    def test_a_well_formed_result_parses(self) -> None:
        result = parse_structured(
            NormalizationResult,
            {
                "groups": [
                    {
                        "normalized_topic": "Strings",
                        "normalized_subtopic": "Indexing",
                        "normalized_description": "Read one character by position.",
                        "reason_for_grouping": "Both teach retrieving characters by index.",
                        "confidence": "high",
                        "candidate_ids": ["c001", "c002"],
                    }
                ]
            },
            stage="normalization",
        )
        assert result.groups[0].candidate_ids == ["c001", "c002"]

    def test_a_group_with_no_members_is_rejected(self) -> None:
        with pytest.raises(MalformedModelOutputError):
            parse_structured(
                NormalizationResult,
                {
                    "groups": [
                        {
                            "normalized_topic": "Strings",
                            "normalized_subtopic": "Indexing",
                            "normalized_description": "Read one character.",
                            "reason_for_grouping": "They match.",
                            "confidence": "high",
                            "candidate_ids": [],
                        }
                    ]
                },
                stage="normalization",
            )

    def test_a_result_with_no_groups_is_rejected(self) -> None:
        with pytest.raises(MalformedModelOutputError):
            parse_structured(NormalizationResult, {"groups": []}, stage="normalization")

    def test_a_missing_rationale_is_rejected(self) -> None:
        """The reason is what makes a merge auditable, so it is not optional."""
        with pytest.raises(MalformedModelOutputError):
            parse_structured(
                NormalizationResult,
                {
                    "groups": [
                        {
                            "normalized_topic": "Strings",
                            "normalized_subtopic": "Indexing",
                            "normalized_description": "Read one character.",
                            "confidence": "high",
                            "candidate_ids": ["c001"],
                        }
                    ]
                },
                stage="normalization",
            )

    def test_prose_instead_of_an_object_is_rejected(self) -> None:
        with pytest.raises(MalformedModelOutputError):
            parse_structured(
                NormalizationResult,
                {"answer": "I grouped them by topic."},
                stage="normalization",
            )


class TestJsonSchema:
    """What is actually handed to the provider must describe the model."""

    @pytest.mark.parametrize("model", [SectionAnalysis, NormalizationResult, ConceptGroup])
    def test_schema_is_a_closed_object(self, model: type) -> None:
        schema = json_schema_for(model)
        assert schema["type"] == "object"
        # extra="forbid" must reach the provider, or the strict contract is only
        # enforced after the tokens have been paid for.
        assert schema["additionalProperties"] is False
        assert schema["required"]

    def test_section_analysis_schema_names_its_fields(self) -> None:
        schema = json_schema_for(SectionAnalysis)
        assert set(schema["properties"]) == {
            "teaches",
            "is_instructional",
            "concepts",
            "confidence",
        }
