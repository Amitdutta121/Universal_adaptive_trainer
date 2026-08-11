"""Identifiers for proposed curriculum items that survive being renamed.

Why not just use the name
    A proposed subtopic is something the professor will rename, reword and
    reorder. If its identity were its display name, every edit would look like a
    deletion plus an insertion: the supporting evidence would detach, and once
    the adaptive engine tracks weakness per subtopic, a rename would silently
    reset a student's measured weakness for that skill.

What identity is instead
    Everything a stable id is built from comes from the **books**, never from
    text the professor can edit:

    * the candidate labels the books themselves used for the concept;
    * the candidate topic labels those candidates declared;
    * a fingerprint of each supporting section's position in its book.

    So renaming "String indexing" to "Indexing strings" leaves the id alone,
    while a genuinely different grouping of sections gets a different id.

Known limitation
    Moving a subtopic to a different topic, or re-running proposal over a
    different set of books, does change the id: identity is defined by the source
    material a concept was derived from, so different source material means a
    different concept. Recorded here rather than hidden, because it matters once
    curriculum editing is implemented.

No pattern matching anywhere
    Normalisation uses character classification only (``str.isalnum``), never
    regular expressions -- consistent with this codebase's rule that structure is
    never recovered by pattern-matching text (ADR-015).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from app.domain.books import SectionSource

#: Separates components inside a fingerprint's canonical string. A unit separator
#: cannot occur in a label, so two different component lists cannot collide by
#: joining to the same string.
_SEPARATOR = "\x1f"

#: Twelve hex characters is 48 bits: collision-proof at curriculum scale, and
#: short enough to appear in a URL and be read aloud.
_DIGEST_LENGTH = 12

TOPIC_PREFIX = "top"
SUBTOPIC_PREFIX = "sub"


def normalize_label(value: str) -> str:
    """Reduce a label to a comparison key: casefolded, alphanumeric words only.

    "Accessing Characters!", "accessing  characters" and "Accessing-Characters"
    all reduce to "accessing characters", so two spellings of one label do not
    produce two identities.
    """
    words: list[str] = []
    current: list[str] = []
    for character in value.casefold():
        if character.isalnum():
            current.append(character)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return " ".join(words)


def slugify(value: str) -> str:
    """A URL- and log-safe rendering of a label. Empty when nothing survives."""
    return normalize_label(value).replace(" ", "-")


def fingerprint(parts: Iterable[str]) -> str:
    """Hash an ordered list of components into a short hex digest."""
    canonical = _SEPARATOR.join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


def source_key(source: SectionSource) -> str:
    """Identify a section by where it sits in its book, not by its database id.

    Row ids change when a book is re-imported from a corrected document; the
    book title plus the printed chapter/section numbers do not. Position within
    the book is included as the fallback for a section the source never numbered,
    so an unnumbered section is still distinguishable from its neighbours.
    """
    return _SEPARATOR.join(
        (
            normalize_label(source.book_title),
            normalize_label(source.chapter_number or ""),
            normalize_label(source.section_number or ""),
            normalize_label(source.section_title or ""),
            str(source.start_page or ""),
        )
    )


def topic_stable_id(candidate_topic_labels: Iterable[str]) -> str:
    """Identity of a topic: the set of book-declared topic labels behind it."""
    keys = sorted({normalize_label(label) for label in candidate_topic_labels})
    return f"{TOPIC_PREFIX}-{fingerprint(keys)}"


def subtopic_stable_id(
    *,
    candidate_labels: Iterable[str],
    candidate_topic_labels: Iterable[str],
    source_keys: Iterable[str],
) -> str:
    """Identity of a subtopic: the book wordings and sections it was merged from.

    The topic labels take part so that two subtopics merged from the same
    wording under genuinely different topics stay distinct. They are the books'
    labels, not the professor's, so a topic rename does not disturb them.
    """
    components = [
        ",".join(sorted({normalize_label(label) for label in candidate_labels})),
        ",".join(sorted({normalize_label(label) for label in candidate_topic_labels})),
        ",".join(sorted(set(source_keys))),
    ]
    return f"{SUBTOPIC_PREFIX}-{fingerprint(components)}"
