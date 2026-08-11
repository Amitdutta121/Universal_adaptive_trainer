"""Professor preference statements inferred from review history."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import PreferenceCategory, PreferenceConfirmationState

PROFILE_VERSION = "1"


def _now() -> datetime:
    return datetime.now(UTC)


def confidence_from_evidence(evidence_count: int, *, confirmed: bool = False) -> float:
    """Map repeated evidence to [0, 1]. One review stays below the soft floor."""
    if evidence_count <= 0:
        return 0.0
    # 1 → ~0.2; 2 → ~0.4; 5 → ~0.7; 10 → ~0.85
    raw = 1.0 - (1.0 / (1.0 + 0.5 * evidence_count))
    if confirmed:
        raw = min(1.0, raw + 0.1)
    return round(min(1.0, raw), 4)


def encode_review_ids(ids: list[int]) -> str:
    return json.dumps(ids)


def decode_review_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(x) for x in json.loads(raw)]


class PreferenceStatement(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    rule_text: str = Field(min_length=1)
    category: PreferenceCategory
    evidence_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_review_ids: list[int] = Field(default_factory=list)
    active: bool = True
    confirmation_state: PreferenceConfirmationState = PreferenceConfirmationState.INFERRED
    profile_version: str = PROFILE_VERSION
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime | None = None
