"""Helpers for deterministic validation reports."""

from __future__ import annotations

from app.validation.report import make_check


def test_make_check_is_deterministic_error() -> None:
    check = make_check("allowed_difficulty", True, "Allowed difficulty")
    assert check.passed is True
    assert check.deterministic is True
    assert check.severity == "error"
    assert check.evidence is None
