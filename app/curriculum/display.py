"""Decode curriculum database fields for server-rendered display."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field

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


def decode_json_list(raw: str | None) -> list:
    """Read a JSON list column without allowing bad display data to break a page."""
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Discarding unreadable JSON list payload")
        return []
    return payload if isinstance(payload, list) else []


def decode_proposal_warnings(raw: str | None) -> list[DisplayProposalWarning]:
    """Read warnings retained on a legacy proposal row for display."""
    warnings: list[DisplayProposalWarning] = []
    for item in decode_json_list(raw):
        try:
            warnings.append(DisplayProposalWarning.model_validate(item))
        except ValueError:
            continue
    return warnings


def decode_metadata(raw: str | None) -> DisplayExtractionMetadata | None:
    """Read legacy proposal metadata, or ``None`` when absent or unreadable."""
    if not raw:
        return None
    try:
        return DisplayExtractionMetadata.model_validate_json(raw)
    except ValueError:
        logger.warning("Discarding unreadable extraction metadata")
        return None
