"""Validate curriculum database fields for API/frontend display.

These shapes belong to the removed LLM proposal pipeline and survive only so
existing rows still render. The columns behind them are plain JSON objects and
lists (see :mod:`app.persistence.types`) rather than typed model columns,
because ``app.persistence`` must not import a subsystem to describe them.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class DisplayProposalWarning(BaseModel):
    """One warning retained on a legacy LLM-generated curriculum version."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    location: str | None = None


class DisplayExtractionMetadata(BaseModel):
    """Legacy LLM proposal metadata used only to render existing rows."""

    model_config = ConfigDict(frozen=True)

    generated_by: str = Field(min_length=1)
    stage_a_version: str = Field(min_length=1)
    stage_b_version: str = Field(min_length=1)
    books_analysed: int = Field(default=0, ge=0)
    sections_analysed: int = Field(default=0, ge=0)
    sections_skipped: int = Field(default=0, ge=0)
    candidates_extracted: int = Field(default=0, ge=0)
    groups_returned: int = Field(default=0, ge=0)


def proposal_warnings(payload: list[object]) -> list[DisplayProposalWarning]:
    """Read warnings retained on a legacy proposal row, skipping unusable items."""
    warnings: list[DisplayProposalWarning] = []
    for item in payload:
        try:
            warnings.append(DisplayProposalWarning.model_validate(item))
        except ValidationError:
            continue
    return warnings


def extraction_metadata(payload: dict | None) -> DisplayExtractionMetadata | None:
    """Read legacy proposal metadata, or ``None`` when absent or no longer valid."""
    if payload is None:
        return None
    try:
        return DisplayExtractionMetadata.model_validate(payload)
    except ValidationError:
        logger.warning("Discarding extraction metadata that no longer validates")
        return None
