"""Draft a taxonomy with the LLM from the professor's own title and description (ADR-052).

The draft is never stored. It is returned to the builder, where the professor
edits it; only saving it there creates a curriculum version, through the same
validated upload path as a hand-built taxonomy. So the model proposes and the
professor decides, which is what ADR-021 protects.

The only input is what the professor writes (:class:`DraftBrief`): a title and
description, and optionally the audience, what it must cover, what to leave out
and how big it should be. No book is read, so a taxonomy can be drafted before
any material is uploaded, and the professor's intent -- not one textbook's
chapter order -- decides the shape.

The instruction says what the rest of the product does with a taxonomy -- topics
are walked in order (the adaptive engine), every subtopic needs about nine
reviewed questions (coverage), and a subtopic's description is the query that
later finds its passage in the course's books (retrieval) -- because those are
what make a draft usable. It names no subject: the description says what the
course is.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.curriculum.stable_ids import normalize_label
from app.curriculum.taxonomy_schema import (
    DESCRIPTION_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SCHEMA_VERSION,
    TaxonomyDocument,
    validate_taxonomy_payload,
)
from app.errors import DomainRuleError
from app.llm.client import StructuredLLMClient, get_structured_client

logger = logging.getLogger(__name__)

DRAFT_SYSTEM_PROMPT = """\
You design the skill map for an adaptive training course, from the instructor's own \
description of it.

How the course will use your answer -- this is why the rules below exist:
- Students are trained topic by topic, in the order you give. A topic is the unit their \
mastery is measured on; they move to the next topic once they have mastered this one.
- A subtopic is one skill a single question can test. Students' weaknesses are tracked per \
subtopic, and each subtopic needs about nine reviewed questions (three at each of three \
difficulties), so every subtopic you add costs the instructor real review work.
- Questions are later written from the course's reading material: each subtopic's topic \
name, name and description are used to search that material for the passage to write \
questions from.

First fill in `analysis`, before writing any topic. Note, briefly:
- the level and audience, and what the instructor asks to emphasise or leave out;
- the skills the course should cover, grouped into areas;
- which skills depend on which, and so the order a student should learn them in.

Then write the taxonomy:
1. Topics in learning order: prerequisites first.
2. Keep to the size the instructor asked for (given with the request). Prefer fewer, \
solid skills to many thin ones.
3. A subtopic names one skill the student can demonstrate ("Interpreting a p-value"), \
not a broad theme ("Statistics basics").
4. Every item under "Must cover" appears, as a topic or a subtopic, in the instructor's \
wording where it already names a skill. Nothing under "Leave out" appears.
5. Stay inside the course the description sets out. Respect its level and audience. \
Do not pad it with neighbouring material because it is often taught alongside.
6. Every topic and subtopic gets a description of one or two sentences. A subtopic's \
description says exactly what the student can do, in the field's standard terms -- it is \
the search text that finds the right reading passage, so be concrete.
7. No two subtopics may overlap: if two could claim the same question, merge them or \
sharpen their descriptions until they cannot.
8. Names are short skill names.
9. `label` is the taxonomy title, shortened if needed.
"""


DraftSize = Literal["compact", "standard", "detailed"]

#: What each size means, in words the model is given and the UI shows.
SIZE_TARGETS: dict[str, str] = {
    "compact": "4 to 6 topics with 2 to 4 subtopics each, about 15 subtopics in all",
    "standard": "6 to 10 topics with 2 to 5 subtopics each, about 30 subtopics in all",
    "detailed": "8 to 14 topics with 3 to 5 subtopics each, about 45 subtopics in all",
}


class DraftBrief(BaseModel):
    """What the professor tells the AI about the taxonomy they want."""

    title: str
    description: str
    audience: str = ""
    must_cover: str = ""
    leave_out: str = ""
    size: DraftSize = "standard"


class _DraftSubtopic(BaseModel):
    name: str
    description: str = ""


class _DraftTopic(BaseModel):
    name: str
    description: str = ""
    subtopics: list[_DraftSubtopic] = Field(default_factory=list)


class _DraftTaxonomy(BaseModel):
    """What the model is asked for. Field order matters: ``analysis`` comes first.

    The model writes fields in schema order, so putting the analysis first makes it
    reason about the course before it commits to a single topic. The document's strict
    checks are left out on purpose: duplicate names and over-long fields are repaired
    after the call rather than rejected by it -- one near-duplicate subtopic is not a
    reason to throw away a whole draft the professor is about to edit anyway.
    """

    analysis: str = Field(
        description="Level and audience, the skills to cover grouped into areas, and the "
        "learning order. Written before the taxonomy."
    )
    label: str
    topics: list[_DraftTopic]


class TaxonomyDraft(BaseModel):
    document: TaxonomyDocument
    analysis: str
    drafted_by: str


def draft_taxonomy(
    brief: DraftBrief, *, client: StructuredLLMClient | None = None
) -> TaxonomyDraft:
    """Propose a taxonomy from what the professor wrote.

    Raises:
        DomainRuleError: the model's answer had nothing usable left after repair.
        LLMRequestError, MalformedModelOutputError: the provider call failed.
    """
    client = client or get_structured_client()
    raw = client.complete_structured(
        system=DRAFT_SYSTEM_PROMPT,
        prompt=draft_user_prompt(brief),
        response_model=_DraftTaxonomy,
    )
    document = _repair(raw, fallback_label=brief.title)
    logger.info(
        "Drafted taxonomy %r: %d topic(s), %d subtopic(s)",
        document.label,
        len(document.topics),
        sum(len(topic.subtopics) for topic in document.topics),
    )
    return TaxonomyDraft(
        document=document, analysis=raw.analysis.strip(), drafted_by=client.description
    )


def draft_user_prompt(brief: DraftBrief) -> str:
    """The user message: the professor's own words, section by section; empty ones are omitted."""
    sections = [
        ("Taxonomy title", brief.title),
        ("Description", brief.description),
        ("Audience and level", brief.audience),
        ("Must cover", brief.must_cover),
        ("Leave out", brief.leave_out),
    ]
    parts = [f"# {heading}\n{text.strip()}" for heading, text in sections if text.strip()]
    parts.append(f"# Size\n{SIZE_TARGETS[brief.size]}")
    return "\n\n".join(parts)


def _clip(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit].strip()


def _repair(raw: _DraftTaxonomy, *, fallback_label: str) -> TaxonomyDocument:
    """Make the model's answer a valid document: dedupe names, clip lengths, drop empties."""
    topics: list[dict] = []
    seen_topics: set[str] = set()
    for topic in raw.topics:
        name = _clip(topic.name, NAME_MAX_LENGTH)
        key = normalize_label(name)
        if not name or key in seen_topics:
            continue
        subtopics: list[dict] = []
        seen_subtopics: set[str] = set()
        for subtopic in topic.subtopics:
            sub_name = _clip(subtopic.name, NAME_MAX_LENGTH)
            sub_key = normalize_label(sub_name)
            if not sub_name or sub_key in seen_subtopics:
                continue
            seen_subtopics.add(sub_key)
            subtopics.append(
                {
                    "name": sub_name,
                    "description": _clip(subtopic.description, DESCRIPTION_MAX_LENGTH),
                }
            )
        if not subtopics:
            continue
        seen_topics.add(key)
        topics.append(
            {
                "name": name,
                "description": _clip(topic.description, DESCRIPTION_MAX_LENGTH),
                "subtopics": subtopics,
            }
        )
    if not topics:
        raise DomainRuleError(
            "The AI draft had no usable topics.",
            detail="Try again with a more detailed description, or build the taxonomy by hand.",
        )
    label = _clip(raw.label, LABEL_MAX_LENGTH) or _clip(fallback_label, LABEL_MAX_LENGTH)
    return validate_taxonomy_payload(
        {"schema_version": SCHEMA_VERSION, "label": label, "topics": topics}
    )
