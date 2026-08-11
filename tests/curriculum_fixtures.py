"""Deterministic stand-ins for the two LLM stages, plus three small textbooks.

The whole curriculum pipeline is exercised without an API key and without a
network call. :class:`ScriptedClient` implements the same
:class:`~app.llm.StructuredLLMClient` protocol the real clients do, so what the
tests drive is the production code path, not a parallel one.

The three books deliberately teach the same skill under three different
headings -- "Accessing Characters", "String Indexing", "Selecting Individual
Characters" -- because collapsing exactly that into one subtopic is what Stage B
exists for.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.curriculum.schema import SectionAnalysis
from app.errors import MalformedModelOutputError

SCHEMA_VERSION = "1"


def to_bytes(document: dict[str, Any]) -> bytes:
    """Serialise a book document as it would arrive from a browser upload."""
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


#: Section heading -> the Stage A analysis to answer with. Keys are matched
#: against the "Section:" line of the prompt the extractor builds.
SECTION_ANALYSES: dict[str, dict[str, Any]] = {
    "Accessing Characters": {
        "teaches": "How to read a single character out of a string using its position.",
        "is_instructional": True,
        "confidence": "high",
        "concepts": [
            {
                "label": "Accessing characters",
                "topic_label": "Strings",
                "definition": "Read one character from a string by its position.",
                "evidence": ["letter = fruit[1]"],
                "confidence": "high",
            }
        ],
    },
    "String Length": {
        "teaches": "How to find how many characters a string contains.",
        "is_instructional": True,
        "confidence": "high",
        "concepts": [
            {
                "label": "Finding string length",
                "topic_label": "Strings",
                "definition": "Determine the number of characters in a string.",
                "evidence": ["len(fruit)"],
                "confidence": "high",
            }
        ],
    },
    "String Indexing": {
        "teaches": "Retrieving characters from a string by index, including negatives.",
        "is_instructional": True,
        "confidence": "high",
        "concepts": [
            {
                "label": "String indexing",
                "topic_label": "Strings",
                "definition": "Retrieve a character from a string using an index.",
                "evidence": ["message[0]", "message[-1]"],
                "confidence": "high",
            }
        ],
    },
    "Slicing Strings": {
        "teaches": "Taking a substring with a start and stop index.",
        "is_instructional": True,
        "confidence": "medium",
        "concepts": [
            {
                "label": "Slicing strings",
                "topic_label": "Strings",
                "definition": "Extract a substring using a start and stop index.",
                "evidence": ["message[0:5]"],
                "confidence": "medium",
            }
        ],
    },
    "Selecting Individual Characters": {
        "teaches": "Picking one character out of a string by counting from zero.",
        "is_instructional": True,
        "confidence": "high",
        "concepts": [
            {
                "label": "Selecting individual characters",
                "topic_label": "Strings",
                "definition": "Select a single character from a string by position.",
                "evidence": ["spam[0]"],
                "confidence": "high",
            }
        ],
    },
    "About This Book": {
        # Front matter: teaches nothing assessable, so it must contribute nothing.
        "teaches": "Front matter describing the book's audience.",
        "is_instructional": False,
        "confidence": "high",
        "concepts": [],
    },
}

#: Candidate label -> the (topic, subtopic) Stage B normalises it to. The three
#: wordings for reading one character all collapse into "Strings / Indexing".
NORMALIZATION_MAP: dict[str, tuple[str, str]] = {
    "Accessing characters": ("Strings", "Indexing"),
    "String indexing": ("Strings", "Indexing"),
    "Selecting individual characters": ("Strings", "Indexing"),
    "Slicing strings": ("Strings", "Slicing"),
    "Finding string length": ("Strings", "Length"),
}

GROUPING_REASONS: dict[str, str] = {
    "Indexing": (
        "All three sections teach retrieving individual characters from strings using indices."
    ),
    "Slicing": "The section teaches extracting a substring using start and stop indices.",
    "Length": "The section teaches measuring how many characters a string contains.",
}


def parse_candidate_lines(prompt: str) -> list[dict[str, str]]:
    """Read the candidate listing back out of a Stage B prompt.

    Plain string splitting on the separators the prompt builder wrote, so the
    fake reacts to what it was actually sent instead of assuming a fixed answer.
    """
    candidates: list[dict[str, str]] = []
    for line in prompt.splitlines():
        if " | label: " not in line:
            continue
        parts = [piece.strip() for piece in line.split(" | ")]
        fields = dict(piece.split(": ", 1) for piece in parts[1:] if ": " in piece)
        fields["candidate_id"] = parts[0]
        candidates.append(fields)
    return candidates


class ScriptedClient:
    """A structured client that answers from a script instead of a provider."""

    def __init__(
        self,
        *,
        analyses: dict[str, dict[str, Any]] | None = None,
        normalization: dict[str, tuple[str, str]] | None = None,
        stage_a_override: dict[str, Any] | None = None,
        stage_b_override: dict[str, Any] | None = None,
        drop_candidate_ids: tuple[str, ...] = (),
    ) -> None:
        self._analyses = SECTION_ANALYSES if analyses is None else analyses
        self._normalization = NORMALIZATION_MAP if normalization is None else normalization
        #: Forces a fixed (possibly malformed) answer, for the failure tests.
        self._stage_a_override = stage_a_override
        self._stage_b_override = stage_b_override
        #: Candidate ids Stage B "forgets" to place, to exercise the warning.
        self._drop = drop_candidate_ids
        self.prompts: list[tuple[str, str]] = []

    @property
    def description(self) -> str:
        return "scripted/test-model"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        self.prompts.append((response_model.__name__, prompt))
        if response_model is SectionAnalysis or response_model.__name__ == "SectionAnalysis":
            payload = self._analyse(prompt)
        else:
            payload = self._normalize(prompt)
        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            raise MalformedModelOutputError(
                "The model did not return a usable structured answer.",
                detail=str(exc)[:400],
            ) from exc

    def _analyse(self, prompt: str) -> dict[str, Any]:
        if self._stage_a_override is not None:
            return self._stage_a_override
        for heading, analysis in self._analyses.items():
            if heading in prompt:
                return analysis
        raise AssertionError(f"No scripted analysis matches this prompt:\n{prompt}")

    def _normalize(self, prompt: str) -> dict[str, Any]:
        if self._stage_b_override is not None:
            return self._stage_b_override

        grouped: dict[tuple[str, str], list[str]] = {}
        for candidate in parse_candidate_lines(prompt):
            if candidate["candidate_id"] in self._drop:
                continue
            key = self._normalization[candidate["label"]]
            grouped.setdefault(key, []).append(candidate["candidate_id"])

        return {
            "groups": [
                {
                    "normalized_topic": topic,
                    "normalized_subtopic": subtopic,
                    "normalized_description": f"What a student can do with {subtopic.lower()}.",
                    "reason_for_grouping": GROUPING_REASONS.get(
                        subtopic, "These sections teach the same skill."
                    ),
                    "confidence": "high",
                    "candidate_ids": ids,
                }
                for (topic, subtopic), ids in grouped.items()
            ]
        }


def _section(number: str, title: str, text: str, start: int) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "text": text,
        "start_page": start,
        "end_page": start + 1,
        "structure_source": "pdf_outline",
    }


def book_a() -> dict[str, Any]:
    """A textbook that calls the skill "Accessing Characters"."""
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "Think Python",
        "author": "Allen B. Downey",
        "chapters": [
            {
                "number": "8",
                "title": "Strings",
                "start_page": 85,
                "end_page": 96,
                "structure_source": "pdf_outline",
                "sections": [
                    _section(
                        "8.1",
                        "Accessing Characters",
                        "A string is a sequence of characters. You can select one with "
                        "the bracket operator: letter = fruit[1].",
                        85,
                    ),
                    _section(
                        "8.2",
                        "String Length",
                        "len is a built-in function that returns the number of "
                        "characters in a string.",
                        87,
                    ),
                ],
            }
        ],
    }


def book_b() -> dict[str, Any]:
    """A textbook that calls the same skill "String Indexing"."""
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "Python Crash Course",
        "author": "Eric Matthes",
        "chapters": [
            {
                "number": "2",
                "title": "Working with Strings",
                "start_page": 20,
                "end_page": 34,
                "structure_source": "pdf_outline",
                "sections": [
                    _section(
                        "2.3",
                        "String Indexing",
                        "Each character in a string has an index. message[0] is the "
                        "first character and message[-1] is the last.",
                        22,
                    ),
                    _section(
                        "2.4",
                        "Slicing Strings",
                        "A slice takes a range of characters: message[0:5] returns the first five.",
                        25,
                    ),
                ],
            }
        ],
    }


def book_c() -> dict[str, Any]:
    """A third textbook, with front matter that teaches nothing assessable."""
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "Automate the Boring Stuff",
        "author": "Al Sweigart",
        "chapters": [
            {
                "number": "0",
                "title": "Introduction",
                "start_page": 1,
                "end_page": 4,
                "structure_source": "pdf_outline",
                "sections": [
                    _section("0.1", "About This Book", "This book is for total beginners.", 1)
                ],
            },
            {
                "number": "6",
                "title": "Manipulating Strings",
                "start_page": 125,
                "end_page": 140,
                "structure_source": "pdf_outline",
                "sections": [
                    _section(
                        "6.1",
                        "Selecting Individual Characters",
                        "You can select a character by counting from zero: spam[0].",
                        125,
                    )
                ],
            },
        ],
    }
