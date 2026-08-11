"""Display decoding for current taxonomy uploads and legacy proposal rows."""

from __future__ import annotations

from app.curriculum import decode_json_list, decode_metadata, decode_proposal_warnings


def test_display_decoders_tolerate_empty_and_malformed_values() -> None:
    assert decode_json_list(None) == []
    assert decode_json_list('{"not": "a list"}') == []
    assert decode_json_list("not-json") == []
    assert decode_metadata(None) is None
    assert decode_metadata("not-json") is None
    assert decode_proposal_warnings(None) == []
    assert decode_proposal_warnings('[{"code": 12}]') == []


def test_display_decoders_preserve_legacy_proposal_fields() -> None:
    metadata = decode_metadata(
        '{"generated_by":"openrouter/model","stage_a_version":"a/1",'
        '"stage_b_version":"b/1","books_analysed":2,"sections_analysed":3,'
        '"sections_skipped":0,"candidates_extracted":4,"groups_returned":5}'
    )
    warnings = decode_proposal_warnings(
        '[{"code":"sections_skipped","message":"One section skipped","location":"Book 1"}]'
    )

    assert metadata is not None
    assert metadata.generated_by == "openrouter/model"
    assert metadata.groups_returned == 5
    assert len(warnings) == 1
    assert warnings[0].message == "One section skipped"
    assert warnings[0].location == "Book 1"
