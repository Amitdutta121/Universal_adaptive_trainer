"""Import professor-authored taxonomies as approved curriculum versions.

The removed LLM proposal pipeline is intentionally not part of this boundary.
Display decoders remain so existing database rows can still be rendered safely.

Beside import sit the two things a version needs after it exists: the generated
instruction that produces a valid document (:mod:`app.curriculum.authoring`), and
the editing and removal of rows an import already wrote
(:mod:`app.curriculum.library`). Neither proposes curriculum; both are ADR-046.
"""

from __future__ import annotations

from app.curriculum.authoring import (
    ALL_FIELDS,
    DOCUMENT_FIELDS,
    EXAMPLE_DOCUMENT,
    SUBTOPIC_FIELDS,
    TOPIC_FIELDS,
    FieldLimit,
    example_json,
    taxonomy_authoring_prompt,
)
from app.curriculum.display import extraction_metadata, proposal_warnings
from app.curriculum.library import CurriculumLibraryService, CurriculumUsage
from app.curriculum.taxonomy_import import SUPPORTED_EXTENSIONS, TaxonomyImportService
from app.curriculum.taxonomy_schema import (
    DESCRIPTION_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SCHEMA_VERSION,
    parse_taxonomy_document,
)

__all__ = [
    "ALL_FIELDS",
    "DESCRIPTION_MAX_LENGTH",
    "DOCUMENT_FIELDS",
    "EXAMPLE_DOCUMENT",
    "LABEL_MAX_LENGTH",
    "NAME_MAX_LENGTH",
    "SCHEMA_VERSION",
    "SUBTOPIC_FIELDS",
    "SUPPORTED_EXTENSIONS",
    "TOPIC_FIELDS",
    "CurriculumLibraryService",
    "CurriculumUsage",
    "FieldLimit",
    "TaxonomyImportService",
    "example_json",
    "extraction_metadata",
    "parse_taxonomy_document",
    "proposal_warnings",
    "taxonomy_authoring_prompt",
]
