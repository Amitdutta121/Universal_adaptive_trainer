"""Stable ids for uploaded taxonomies — derived from names at import time."""

from __future__ import annotations

from app.curriculum.stable_ids import (
    SUBTOPIC_PREFIX,
    TOPIC_PREFIX,
    fingerprint,
    normalize_label,
)


def topic_id_from_name(name: str) -> str:
    return f"{TOPIC_PREFIX}-{fingerprint([normalize_label(name)])}"


def subtopic_id_from_names(topic_name: str, subtopic_name: str) -> str:
    parts = [normalize_label(topic_name), normalize_label(subtopic_name)]
    return f"{SUBTOPIC_PREFIX}-{fingerprint(parts)}"
