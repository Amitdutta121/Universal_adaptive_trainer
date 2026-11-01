"""Facets of a subtopic: the distinct things a question about it can assess (ADR-063 point 6).

A cell (subtopic x difficulty) asked for several questions used to get several rewordings of
one question. Here each subtopic's facets are listed **once** by a model call and stored
(``subtopic_facets``); a round gives each target of a cell a facet that the cell's questions
-- approved or awaiting review, as :func:`app.generation.rounds.cell_counts` counts them --
do not cover yet, and never the same facet to two targets of one cell. A question records
its facet in its frozen spec. A cell whose facets are all covered is **saturated**: it gets
no target and the round says so, instead of generating another rewording.

Listing the facets is the only model call, made from the round's background job, never from
a request: planning reads the stored lists only.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Collection

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionStatus
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import QuestionRow, SubtopicFacetRow, SubtopicRow

logger = logging.getLogger(__name__)

MIN_FACETS = 4
MAX_FACETS = 8
#: Characters kept of one facet.
FACET_CHARS = 160

#: Questions that cover a facet: approved, or still waiting for the professor.
_COVERING_STATUSES = (
    QuestionStatus.APPROVED,
    QuestionStatus.GENERATED,
    QuestionStatus.VALIDATION_PASSED,
)

SYSTEM = (
    "You plan assessment questions for one subtopic of a course. List the distinct facets of "
    "the subtopic a question could assess: each one a different idea, skill or common mistake, "
    "not a different wording or difficulty of the same question. Each facet is a short noun "
    "phrase of at most 12 words."
)


class FacetList(BaseModel):
    facets: list[str] = Field(min_length=MIN_FACETS, max_length=MAX_FACETS)


def facets_prompt(subtopic: SubtopicRow, topic_name: str) -> str:
    description = f"\nDescription: {subtopic.description}" if subtopic.description else ""
    return (
        f"Topic: {topic_name}\nSubtopic: {subtopic.name}{description}\n\n"
        f"List {MIN_FACETS} to {MAX_FACETS} facets of this subtopic."
    )


def _clean(facets: list[str]) -> list[str]:
    cleaned = (" ".join(facet.split())[:FACET_CHARS] for facet in facets)
    return list(dict.fromkeys(facet for facet in cleaned if facet))[:MAX_FACETS]


def stored_facets(session: Session, subtopic_ids: Collection[int]) -> dict[int, list[str]]:
    """The facets already listed for ``subtopic_ids``; a subtopic never listed is absent."""
    if not subtopic_ids:
        return {}
    rows = session.scalars(
        select(SubtopicFacetRow).where(SubtopicFacetRow.subtopic_id.in_(list(subtopic_ids)))
    )
    return {row.subtopic_id: list(row.facets or []) for row in rows}


def facets_for(
    session: Session,
    subtopic: SubtopicRow,
    topic_name: str,
    *,
    client: StructuredLLMClient | None = None,
) -> list[str]:
    """The subtopic's facets: the stored list, or one model call whose answer is stored.

    Flushes; the caller commits. A provider failure propagates and nothing is stored.
    """
    stored = stored_facets(session, [subtopic.id]).get(subtopic.id)
    if stored is not None:
        return stored
    llm = client or get_structured_client()
    answer = llm.complete_structured(
        system=SYSTEM, prompt=facets_prompt(subtopic, topic_name), response_model=FacetList
    )
    facets = _clean(answer.facets)
    session.add(SubtopicFacetRow(subtopic_id=subtopic.id, facets=facets, model=llm.description))
    session.flush()
    logger.info("Listed %s facets for subtopic %s.", len(facets), subtopic.id)
    return facets


def covered_facets(
    session: Session, curriculum_version_id: int
) -> dict[tuple[int, Difficulty], Counter[str]]:
    """How many questions of each cell assess each facet, from the facets in their specs."""
    stmt = select(QuestionRow).where(
        QuestionRow.curriculum_version_id == curriculum_version_id,
        QuestionRow.status.in_(_COVERING_STATUSES),
    )
    covered: dict[tuple[int, Difficulty], Counter[str]] = {}
    for question in session.scalars(stmt):
        spec = question.spec if isinstance(question.spec, dict) else {}
        facet = spec.get("facet")
        if not isinstance(facet, str) or not facet:
            continue
        subtopics = set(question.subtopic_ids)
        if question.target_subtopic_id is not None:
            subtopics.add(question.target_subtopic_id)
        for subtopic_id in subtopics:
            cell = (subtopic_id, Difficulty(question.difficulty))
            covered.setdefault(cell, Counter())[facet] += 1
    return covered


def open_facets(facets: list[str], covered: Collection[str]) -> list[str]:
    """The facets not yet covered, in listed order."""
    return [facet for facet in facets if facet not in covered]
