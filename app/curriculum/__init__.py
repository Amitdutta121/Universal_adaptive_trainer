"""Import professor-authored taxonomies as approved curriculum versions.

The removed LLM proposal pipeline is intentionally not part of this boundary.
Display decoders remain so existing database rows can still be rendered safely.
"""

from __future__ import annotations

from app.curriculum.display import (
    decode_json_list,
    decode_metadata,
    decode_proposal_warnings,
)
from app.curriculum.taxonomy_import import TaxonomyImportService
from app.curriculum.taxonomy_schema import SCHEMA_VERSION, parse_taxonomy_document

__all__ = [
    "SCHEMA_VERSION",
    "TaxonomyImportService",
    "decode_json_list",
    "decode_metadata",
    "decode_proposal_warnings",
    "parse_taxonomy_document",
]
