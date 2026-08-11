"""Book JSON document builders for tests.

Fixtures are plain dictionaries so a test can corrupt one field and assert the
exact validation failure, which is the point of a declared-structure contract.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

SCHEMA_VERSION = "1"


def think_python() -> dict[str, Any]:
    """A well-formed two-chapter textbook matching the professor-facing milestone."""
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "Think Python",
        "author": "Allen B. Downey",
        "source_filename": "think_python.pdf",
        "producer": "example-converter 1.0",
        "page_count": 292,
        "chapters": [
            {
                "number": "1",
                "title": "The Way of the Program",
                "start_page": 17,
                "end_page": 30,
                "structure_source": "pdf_outline",
                "sections": [
                    {
                        "number": "1.1",
                        "title": "What Is a Program?",
                        "start_page": 17,
                        "end_page": 18,
                        "text": "A program is a sequence of instructions.",
                        "structure_source": "pdf_outline",
                    },
                    {
                        "number": "1.2",
                        "title": "Running Python",
                        "start_page": 18,
                        "end_page": 20,
                        "text": "You can run Python in an interpreter.",
                        "structure_source": "pdf_outline",
                    },
                ],
            },
            {
                "number": "2",
                "title": "Variables, Expressions and Statements",
                "start_page": 31,
                "end_page": 44,
                "structure_source": "pdf_outline",
                "sections": [
                    {
                        "number": "2.1",
                        "title": "Values and Types",
                        "start_page": 31,
                        "end_page": 33,
                        "text": "A value is a basic thing a program works with.",
                        "structure_source": "pdf_outline",
                    },
                    {
                        "number": "2.2",
                        "title": "Variables",
                        "start_page": 33,
                        "end_page": 35,
                        "text": "A variable is a name that refers to a value.",
                        "structure_source": "pdf_outline",
                    },
                ],
            },
        ],
    }


def minimal() -> dict[str, Any]:
    """The smallest document the schema accepts."""
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "Tiny Book",
        "chapters": [{"sections": [{"text": "The only section."}]}],
    }


def with_caveats() -> dict[str, Any]:
    """A document that validates but declares defects and a guessed boundary."""
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "Uncertain Book",
        "chapters": [
            {
                "number": None,
                "title": None,
                "start_page": 1,
                "end_page": 2,
                "structure_source": "producer_inferred",
                "sections": [
                    {
                        "number": None,
                        "title": None,
                        "start_page": 1,
                        "end_page": 2,
                        "text": "Text whose boundaries the producer had to guess.",
                        "structure_source": "producer_inferred",
                        "warnings": [
                            {
                                "code": "missing_heading",
                                "message": "No heading was printed here.",
                                "severity": "defect",
                            }
                        ],
                    }
                ],
            }
        ],
        "warnings": [
            {
                "code": "producer_inferred_structure",
                "message": "The source had no table of contents.",
                "severity": "defect",
            }
        ],
    }


def informational_only() -> dict[str, Any]:
    """A clean document whose only warning states a fact, not a defect."""
    document = minimal()
    document["warnings"] = [
        {
            "code": "no_page_numbers",
            "message": "The source carries no page numbers.",
            "severity": "info",
        }
    ]
    return document


def to_bytes(document: dict[str, Any]) -> bytes:
    """Serialise a document as it would arrive from a browser upload."""
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def without(document: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Copy a document with top-level keys removed."""
    copy = deepcopy(document)
    for key in keys:
        copy.pop(key, None)
    return copy
