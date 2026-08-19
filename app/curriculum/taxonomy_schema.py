"""The fixed Topic → Subtopic taxonomy document uploaded by the professor."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.curriculum.stable_ids import normalize_label
from app.errors import InvalidTaxonomyDocumentError

SCHEMA_VERSION = "1"

#: Length bounds, named once so the schema, the request models that edit these
#: fields, and the authoring guide cannot state three different limits.
LABEL_MAX_LENGTH = 200
NAME_MAX_LENGTH = 300
DESCRIPTION_MAX_LENGTH = 2000


class TaxonomySubtopic(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)


class TaxonomyTopic(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)
    subtopics: list[TaxonomySubtopic] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_subtopic_names(self) -> TaxonomyTopic:
        seen: set[str] = set()
        for sub in self.subtopics:
            key = normalize_label(sub.name)
            if key in seen:
                raise ValueError(f"duplicate subtopic name {sub.name!r}")
            seen.add(key)
        return self


class TaxonomyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1"]
    label: str = Field(min_length=1, max_length=LABEL_MAX_LENGTH)
    topics: list[TaxonomyTopic] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_topic_names(self) -> TaxonomyDocument:
        seen: set[str] = set()
        for topic in self.topics:
            key = normalize_label(topic.name)
            if key in seen:
                raise ValueError(f"duplicate topic name {topic.name!r}")
            seen.add(key)
        return self


def parse_taxonomy_document(data: bytes) -> TaxonomyDocument:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTaxonomyDocumentError(
            "The taxonomy file is not valid UTF-8 JSON.",
            detail=str(exc),
        ) from exc
    if not isinstance(payload, dict):
        raise InvalidTaxonomyDocumentError(
            "The taxonomy file must be a JSON object.",
            detail=f"Got {type(payload).__name__}.",
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise InvalidTaxonomyDocumentError(
            "Unsupported taxonomy schema_version.",
            detail=f"Expected {SCHEMA_VERSION!r}, got {payload.get('schema_version')!r}.",
        )
    try:
        return TaxonomyDocument.model_validate(payload)
    except ValidationError as exc:
        raise InvalidTaxonomyDocumentError(
            "The taxonomy document did not satisfy the schema.",
            detail="; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:8]
            ),
        ) from exc
