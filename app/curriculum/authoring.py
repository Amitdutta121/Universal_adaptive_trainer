"""The instruction that produces a taxonomy document, and the limits it must obey.

A professor does not hand-write a Topic -> Subtopic taxonomy in JSON, and this
application will never derive one for them: curriculum is declared by the
professor, never proposed by a model (ADR-021). What is in scope is saying,
exactly and in one place, what a valid document looks like -- so the professor
can hand that to an assistant and get back something this application accepts.

Why the guide is generated rather than written out
    A description typed into a template drifts from the schema the moment a limit
    changes, and the drift is invisible: the professor gets a document that reads
    as correct and is refused on upload. Everything variable here -- the schema
    version, the accepted extension, and every length bound -- is read from
    :mod:`app.curriculum.taxonomy_schema` and
    :mod:`app.curriculum.taxonomy_import`, so the guide cannot describe a
    document the validator would refuse.

What replaces the vocabulary section
    A book document has three closed vocabularies to enumerate; a taxonomy
    document has none. What a professor cannot guess instead are the two rules
    that make an otherwise reasonable document fail: an unknown key is rejected
    rather than ignored, and duplicate names are compared after normalisation, so
    "String indexing" and "string-indexing" collide. Both are stated explicitly,
    beside a field reference read out of the models themselves.

What the guide is not
    Advisory, entirely. It grants nothing. Whatever comes back is validated in
    full by :func:`app.curriculum.taxonomy_schema.parse_taxonomy_document`, and a
    document that followed the instruction loosely is refused exactly like any
    other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from app.curriculum.taxonomy_import import SUPPORTED_EXTENSIONS
from app.curriculum.taxonomy_schema import (
    SCHEMA_VERSION,
    TaxonomyDocument,
    TaxonomySubtopic,
    TaxonomyTopic,
)

#: Fields whose bound counts items rather than characters.
_LIST_FIELDS = frozenset({"topics", "subtopics"})


@dataclass(frozen=True)
class FieldLimit:
    """One field of the taxonomy contract, and the bounds the validator enforces.

    The model carries the rule for a developer, in its ``Field(...)`` call. This
    carries it for the person writing a document, and for the assistant being
    asked to write one on their behalf.
    """

    path: str
    required: bool
    #: ``"text"`` or ``"list"`` -- what a professor sees, not a Python type name.
    kind: str
    min_length: int | None
    max_length: int | None
    meaning: str


def _bound(field: FieldInfo, attr: str) -> int | None:
    """Read ``min_length``/``max_length`` off a field's constraint metadata.

    By attribute presence rather than by importing ``annotated_types``: that
    package reaches this process only as a transitive dependency of pydantic, and
    naming it here would make the guide depend on something never declared.
    """
    value = next((getattr(m, attr) for m in field.metadata if hasattr(m, attr)), None)
    return None if value is None else int(value)


def _limits(
    model: type[BaseModel], prefix: str, meanings: dict[str, str]
) -> tuple[FieldLimit, ...]:
    """Build the reference, insisting every field of ``model`` is described.

    Iterating ``model.model_fields`` rather than ``meanings`` is the point: a
    field added to the contract without a professor-facing meaning fails here, at
    import, instead of quietly going missing from the guide a professor relies on.
    """
    missing = [name for name in model.model_fields if name not in meanings]
    if missing:
        raise RuntimeError(f"{model.__name__} fields have no professor-facing meaning: {missing}")
    return tuple(
        FieldLimit(
            path=f"{prefix}{name}",
            required=field.is_required(),
            kind="list" if name in _LIST_FIELDS else "text",
            min_length=_bound(field, "min_length"),
            max_length=_bound(field, "max_length"),
            meaning=meanings[name],
        )
        for name, field in model.model_fields.items()
    )


DOCUMENT_FIELDS = _limits(
    TaxonomyDocument,
    "",
    {
        "schema_version": f'exactly "{SCHEMA_VERSION}" -- checked before anything else',
        "label": "what this taxonomy is called, e.g. the course it belongs to",
        "topics": "the topics, in the order you want them shown",
    },
)

TOPIC_FIELDS = _limits(
    TaxonomyTopic,
    "topics[].",
    {
        "name": "the topic's display name -- the unit a student's mastery is tracked for",
        "description": "what the topic covers, in a sentence",
        "subtopics": "the skills this topic is made of",
    },
)

SUBTOPIC_FIELDS = _limits(
    TaxonomySubtopic,
    "topics[].subtopics[].",
    {
        "name": "the subtopic's display name -- the unit a student's weakness is tracked for",
        "description": "the specific skill this subtopic names",
    },
)

ALL_FIELDS: tuple[FieldLimit, ...] = (*DOCUMENT_FIELDS, *TOPIC_FIELDS, *SUBTOPIC_FIELDS)


#: A complete document this application accepts. Held here rather than read from
#: ``docs/`` so serving the guide never depends on a repository path or on the
#: process working directory -- and so ``schema_version`` is interpolated from
#: the contract rather than frozen as a literal. ``tests/test_curriculum_authoring.py``
#: parses it with the real validator and pins it to
#: ``docs/taxonomy_document_example.json``, so the two cannot disagree.
EXAMPLE_DOCUMENT: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "label": "Introductory Python",
    "topics": [
        {
            "name": "Variables",
            "description": "Creating names, assigning values, and understanding types.",
            "subtopics": [
                {
                    "name": "Assignment and rebinding",
                    "description": "Using = to bind a name to a value and reassign it later.",
                },
                {
                    "name": "Basic types",
                    "description": "Working with int, float, str, and bool values.",
                },
            ],
        },
        {
            "name": "Loops",
            "description": "Repeating actions with for and while loops.",
            "subtopics": [
                {
                    "name": "for loops over sequences",
                    "description": "Iterating over strings, lists, and other iterables.",
                },
                {
                    "name": "while loops",
                    "description": "Repeating while a condition remains true.",
                },
                {
                    "name": "Loop control",
                    "description": "Using break and continue to alter loop flow.",
                },
            ],
        },
    ],
}


def example_json() -> str:
    """The example document as the JSON text a professor would upload."""
    return json.dumps(EXAMPLE_DOCUMENT, indent=2)


def _limit_line(limit: FieldLimit) -> str:
    need = "required" if limit.required else 'optional, defaults to ""'
    if limit.kind == "list":
        bound = f"at least {limit.min_length}" if limit.min_length else "a list"
    elif limit.max_length is None:
        return f"  - `{limit.path}` ({need}) -- {limit.meaning}"
    elif limit.min_length:
        bound = f"{limit.min_length} to {limit.max_length} characters"
    else:
        bound = f"at most {limit.max_length} characters"
    return f"  - `{limit.path}` ({need}, {bound}) -- {limit.meaning}"


def _field_reference() -> str:
    lines = ["Every field, and every limit the validator enforces:"]
    lines.extend(_limit_line(limit) for limit in ALL_FIELDS)
    return "\n".join(lines)


def taxonomy_authoring_prompt(*, max_upload_mb: int) -> str:
    """The copy-and-paste instruction that turns a syllabus into a taxonomy document.

    Args:
        max_upload_mb: the configured upload limit, so the instruction can state
            the size the reply has to fit inside rather than leaving the professor
            to discover it on a rejected upload.

    Returns:
        Plain text, meant to be pasted into an assistant above a syllabus or a
        list of topics.
    """
    extensions = ", ".join(SUPPORTED_EXTENSIONS)
    return "\n\n".join(
        [
            "# Convert a Python curriculum into a taxonomy JSON document",
            (
                "You are converting a course outline into a fixed Topic -> Subtopic taxonomy "
                "for an adaptive Python training platform. The platform never invents "
                "curriculum: this document is the whole definition of what a student can be "
                "trained on, and what their mastery is measured against. Your reply is "
                "validated strictly on upload and is rejected in full if anything is wrong."
            ),
            (
                "## What I will give you\n"
                "A syllabus, a table of contents, or a list of the topics I teach, pasted "
                "below this instruction. Work only from that -- do not add topics I did not "
                "name because they are usually taught alongside the ones I did."
            ),
            (
                "## Rules you must not break\n"
                "1. Reply with exactly one JSON object and nothing else -- no prose before or "
                "after it, no markdown code fence, no trailing commentary.\n"
                "2. Use only the field names listed below. An unknown or misspelled key is "
                "rejected outright: the document is not extensible, and a stray field is never "
                "ignored.\n"
                "3. Every topic needs at least one subtopic, and the document needs at least "
                "one topic. A topic I named with no subdivisions of its own becomes one "
                "subtopic naming that same skill.\n"
                "4. Topic names must be unique, and subtopic names must be unique within their "
                "topic. Uniqueness is checked after normalising case, punctuation and spacing, "
                'so "String indexing", "string  indexing" and "String-Indexing" all count as '
                "the same name and the second one is a rejection.\n"
                "5. A subtopic is the unit a student's weakness is measured on, so make it one "
                "assessable skill -- something a single question could test. A topic is the "
                "unit mastery is measured on, so keep it broad enough to hold several.\n"
                "6. Name skills, not book sections. This document is not tied to any textbook, "
                "so it must not cite page numbers, chapter numbers or one book's wording.\n"
                "7. Descriptions are optional but wanted. They are shown to me when I review "
                "the hierarchy, and they are what tells two similarly named skills apart. "
                "Never write a description that only restates the name."
            ),
            ("## The shape, with every field in use\n```json\n" + example_json() + "\n```"),
            "## " + _field_reference(),
            (
                "## Check before you answer\n"
                "- Is every topic and subtopic one I named, or one that follows directly from "
                "what I named?\n"
                "- Would any two names collide once case, spacing and punctuation are ignored?\n"
                "- Does every topic have at least one subtopic?\n"
                "- Is each subtopic small enough that one question could assess it?\n"
                "- Does the JSON parse, and does it use only the fields listed above?\n"
                f"- Will the reply fit in a {extensions} file of at most {max_upload_mb} MB? A "
                "taxonomy is small; if you are anywhere near that limit you have written prose "
                "that belongs in a description, or invented topics I did not ask for."
            ),
            "## The curriculum follows\n(paste your syllabus or topic list here)",
        ]
    )
