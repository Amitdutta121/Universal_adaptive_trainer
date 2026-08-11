"""Helpers for building deterministic validation checks."""

from __future__ import annotations

from app.domain.questions import QuestionCheck


def make_check(
    name: str,
    passed: bool,
    detail: str,
    evidence: str | None = None,
) -> QuestionCheck:
    """Build a deterministic error-severity check."""
    return QuestionCheck(
        name=name,
        passed=passed,
        deterministic=True,
        severity="error",
        detail=detail,
        evidence=evidence,
    )
