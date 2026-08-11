"""Display validation for legacy curriculum proposal rows.

The columns behind these helpers decode themselves (``app.persistence.types``),
so what is left to check here is that a payload which no longer satisfies the
display model is skipped rather than raised.
"""

from __future__ import annotations

from app.curriculum import extraction_metadata, proposal_warnings


def test_display_validators_tolerate_absent_and_unusable_values() -> None:
    assert extraction_metadata(None) is None
    assert extraction_metadata({"generated_by": "only-one-field"}) is None
    assert proposal_warnings([]) == []
    assert proposal_warnings([{"code": 12}]) == []


def test_display_validators_preserve_legacy_proposal_fields() -> None:
    metadata = extraction_metadata(
        {
            "generated_by": "openrouter/model",
            "stage_a_version": "a/1",
            "stage_b_version": "b/1",
            "books_analysed": 2,
            "sections_analysed": 3,
            "sections_skipped": 0,
            "candidates_extracted": 4,
            "groups_returned": 5,
        }
    )
    warnings = proposal_warnings(
        [{"code": "sections_skipped", "message": "One section skipped", "location": "Book 1"}]
    )

    assert metadata is not None
    assert metadata.generated_by == "openrouter/model"
    assert metadata.groups_returned == 5
    assert len(warnings) == 1
    assert warnings[0].message == "One section skipped"
    assert warnings[0].location == "Book 1"


def test_unusable_warning_items_are_skipped_individually() -> None:
    warnings = proposal_warnings(
        [
            {"code": 12},
            {"code": "sections_skipped", "message": "Kept"},
        ]
    )

    assert [warning.message for warning in warnings] == ["Kept"]
