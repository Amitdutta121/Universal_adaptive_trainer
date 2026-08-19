"""The instruction that produces a book document, and the vocabulary it may use.

A professor does not hand-write a book JSON document, and this application will
never produce one for them: extracting structure is out of scope here (ADR-015,
ADR-016). What is in scope is saying, exactly and in one place, what a valid
document looks like -- so the professor can hand that to an assistant, or to a
converter they wrote, and get something back that this application accepts.

Why the prompt is generated rather than written out
    A prompt typed into a template drifts from the schema the moment a field or
    an enum value changes, and the drift is invisible: the professor gets a
    document that reads as correct and is refused on upload. Everything variable
    here -- the schema version, the accepted extensions, every closed vocabulary
    -- is read from the contract itself, and ``tests/test_ingestion_authoring.py``
    fails if a vocabulary gains a value this module cannot describe.

What the prompt is not
    Advisory, entirely. It grants nothing. Whatever comes back is validated in
    full by :func:`app.ingestion.schema.parse_book_document`, and a document that
    followed the instruction loosely is refused exactly like any other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.enums import ExtractionWarningCode, StructureSource, WarningSeverity
from app.ingestion.schema import SCHEMA_VERSION
from app.ingestion.storage import SUPPORTED_EXTENSIONS


@dataclass(frozen=True)
class VocabularyTerm:
    """One value of a closed vocabulary, and what it means to a professor.

    The enum member carries the meaning for a developer, in its comment. This
    carries it for the person choosing between the values, and for the assistant
    being asked to choose on their behalf.
    """

    value: str
    meaning: str


def _terms(vocabulary: type[Enum], meanings: dict[Any, str]) -> tuple[VocabularyTerm, ...]:
    """Build the term list, insisting every member of ``vocabulary`` is described.

    Iterating the enum rather than the dictionary is the point: a value added to
    the vocabulary without a meaning fails here, at import, instead of quietly
    going missing from the instruction a professor relies on.
    """
    missing = [member.value for member in vocabulary if member not in meanings]
    if missing:
        raise RuntimeError(f"Vocabulary values have no professor-facing meaning: {missing}")
    return tuple(
        VocabularyTerm(value=str(member.value), meaning=meanings[member]) for member in vocabulary
    )


STRUCTURE_SOURCE_TERMS = _terms(
    StructureSource,
    {
        StructureSource.PDF_OUTLINE: (
            "the PDF's own outline or table of contents stated this boundary"
        ),
        StructureSource.MARKDOWN_HEADING: (
            "an explicit heading in a structured source (Markdown, HTML) stated it"
        ),
        StructureSource.MANUAL: "a person read the source and decided this boundary",
        StructureSource.STRUCTURED_JSON: (
            "the source states the boundary without saying where it came from"
        ),
        StructureSource.PRODUCER_INFERRED: (
            "you had to guess where this unit begins or ends -- it marks the unit low "
            "confidence and makes the whole book partial, which is the honest outcome"
        ),
    },
)

WARNING_CODE_TERMS = _terms(
    ExtractionWarningCode,
    {
        ExtractionWarningCode.NO_PAGE_NUMBERS: "the source carries no page numbers to cite",
        ExtractionWarningCode.PRODUCER_INFERRED_STRUCTURE: "one or more boundaries were guessed",
        ExtractionWarningCode.MISSING_HEADING: (
            "a heading exists in the source but its text could not be read"
        ),
        ExtractionWarningCode.SOURCE_TEXT_UNREADABLE: (
            "part of the source could not be read and is absent from this document"
        ),
        ExtractionWarningCode.SECTION_TEXT_TRUNCATED: "section text was shortened",
        ExtractionWarningCode.METADATA_UNAVAILABLE: "the title or author could not be determined",
        ExtractionWarningCode.OTHER: "anything else; the message must explain it",
    },
)

WARNING_SEVERITY_TERMS = _terms(
    WarningSeverity,
    {
        WarningSeverity.DEFECT: (
            "something was lost, incomplete or guessed at -- the book imports as partial"
        ),
        WarningSeverity.INFO: "true and worth stating, but not a fault in the document",
    },
)


#: A valid document, small enough to sit inside a prompt and complete enough to
#: answer the questions a producer actually has: what a missing heading looks
#: like, where warnings go, and that ``text`` is the source's prose rather than a
#: summary of it. ``tests/test_ingestion_authoring.py`` imports it and validates
#: it through the real parser, so the example cannot rot.
EXAMPLE_DOCUMENT: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "title": "Think Python",
    "author": "Allen B. Downey",
    "source_filename": "think_python.pdf",
    "producer": "claude-opus-5, hand-checked",
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
                    "text": (
                        "A program is a sequence of instructions that specifies how to "
                        "perform a computation. The computation might be something "
                        "mathematical, such as solving a system of equations, but it can "
                        "also be a symbolic computation, such as searching and replacing "
                        "text in a document."
                    ),
                    "structure_source": "pdf_outline",
                },
                {
                    "number": None,
                    "title": None,
                    "start_page": 19,
                    "end_page": 19,
                    "text": (
                        "    print('Hello, World!')\n\n"
                        "The quotation marks mark the beginning and end of the text to be "
                        "displayed; they do not appear in the result."
                    ),
                    "structure_source": "producer_inferred",
                    "warnings": [
                        {
                            "code": "missing_heading",
                            "message": "This passage follows 1.1 under no heading of its own.",
                            "location": "page 19",
                            "severity": "info",
                        }
                    ],
                },
            ],
        }
    ],
    "warnings": [
        {
            "code": "producer_inferred_structure",
            "message": "The boundary of the unheaded passage on page 19 was guessed.",
            "severity": "defect",
        }
    ],
}


def example_json() -> str:
    """The example document as the JSON text a professor would upload."""
    return json.dumps(EXAMPLE_DOCUMENT, indent=2)


def _vocabulary_block(title: str, terms: tuple[VocabularyTerm, ...]) -> str:
    lines = [f"{title}:"]
    lines.extend(f'  - "{term.value}" -- {term.meaning}' for term in terms)
    return "\n".join(lines)


def book_authoring_prompt(*, max_upload_mb: int) -> str:
    """The copy-and-paste instruction that turns textbook text into a document.

    Args:
        max_upload_mb: the configured upload limit, so the instruction can state
            the size the reply has to fit inside rather than leaving the professor
            to discover it on a rejected upload.

    Returns:
        Plain text, meant to be pasted into an assistant above the source text.
    """
    extensions = ", ".join(SUPPORTED_EXTENSIONS)
    return "\n\n".join(
        [
            "# Convert a Python textbook into a book JSON document",
            (
                "You are converting textbook material into a structured JSON document for an "
                "adaptive Python training platform. The platform never guesses a book's "
                "structure, so this document has to declare it. Your reply is validated "
                "strictly on upload, and is rejected in full if anything is wrong."
            ),
            (
                "## What I will give you\n"
                "The text of a textbook, or of one chapter at a time, pasted below this "
                "instruction. Work only from that text."
            ),
            (
                "## Rules you must not break\n"
                "1. Reply with exactly one JSON object and nothing else -- no prose before or "
                "after it, no markdown code fence, no trailing commentary.\n"
                "2. Copy section text VERBATIM into `text`. Never summarise, paraphrase, "
                "shorten, translate or improve it, and never write prose that was not in the "
                "source. Exam questions are generated from this text; invented text produces "
                "questions about a book nobody wrote.\n"
                "3. If you did have to shorten a section, keep what you have and declare it: "
                'add a warning with code "section_text_truncated" and severity "defect". A '
                "declared defect is fine. An undeclared one is not.\n"
                "4. Never invent a heading. Where the source printed no title for a unit, set "
                '`"title": null` and the platform labels it by number or page range. The same '
                "goes for `number`, `author` and every page field: `null` when the source does "
                "not state it.\n"
                "5. Use only the field names listed below. An unknown or misspelled key is "
                "rejected -- the document is not extensible.\n"
                "6. Every chapter needs at least one section, and every section needs "
                "non-empty `text`. A chapter with no subdivisions becomes one section holding "
                "its body. Skip front matter that carries no instructional text rather than "
                "emitting an empty section.\n"
                "7. `end_page` may never be smaller than `start_page`, and page numbers start "
                "at 1."
            ),
            ("## The shape, with every field in use\n```json\n" + example_json() + "\n```"),
            (
                "## Field reference\n"
                f'- `schema_version` (required) -- exactly "{SCHEMA_VERSION}".\n'
                "- `title` (required) -- the book's title, as printed.\n"
                "- `author`, `source_filename`, `page_count` -- only when the source states "
                "them.\n"
                "- `producer` -- what made this document. Name the model and say a person "
                'checked it, e.g. "claude-opus-5, hand-checked". Provenance only; it is never '
                "interpreted.\n"
                "- `chapters[]` (required, at least one) -- `number`, `title`, `start_page`, "
                "`end_page`, `structure_source`, `confidence`, `sections`.\n"
                "- `sections[]` (required, at least one per chapter) -- `number`, `title`, "
                "`start_page`, `end_page`, `text`, `structure_source`, `confidence`, "
                "`warnings`.\n"
                "- `warnings[]` -- allowed on the document and on any section: `code`, "
                "`message`, `location` (optional), `severity`."
            ),
            (
                "## Closed vocabularies -- any other value is rejected\n"
                + _vocabulary_block("`structure_source`", STRUCTURE_SOURCE_TERMS)
                + "\n\n"
                + _vocabulary_block("warning `code`", WARNING_CODE_TERMS)
                + "\n\n"
                + _vocabulary_block("warning `severity`", WARNING_SEVERITY_TERMS)
            ),
            (
                "## Check before you answer\n"
                "- Is every `text` value the source's own words, in full?\n"
                "- Did you invent a heading, a page number or an author? Replace it with "
                "`null`.\n"
                "- Is every `structure_source` honest -- `producer_inferred` wherever you "
                "guessed a boundary?\n"
                "- Does the JSON parse, and does it use only the fields listed above?\n"
                f"- Will the reply fit in a {extensions} file of at most {max_upload_mb} MB? If "
                "the book is larger, convert a few chapters at a time and tell me which range "
                "you covered, rather than silently truncating a section."
            ),
            "## The source text follows\n(paste the textbook text here)",
        ]
    )
