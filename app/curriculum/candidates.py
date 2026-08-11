"""Candidate concepts: Stage A output bound to the section it came from.

Stage A analyses one section at a time and knows nothing about identifiers.
Stage B works over every candidate from every book at once and must be able to
refer to them, so this module assigns each candidate a short id and keeps the
binding between that id, the concept, and the section's
:class:`~app.domain.books.SectionSource`.

The binding is what makes the whole pipeline auditable: an id in Stage B's answer
resolves back to a concept, which resolves back to a book, chapter, section and
page range.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.curriculum.schema import CandidateConcept, SectionAnalysis
from app.curriculum.stable_ids import source_key
from app.domain.books import SectionSource


@dataclass(frozen=True)
class AnalysedSection:
    """One section's Stage A result, with the section it describes."""

    source: SectionSource
    analysis: SectionAnalysis


@dataclass(frozen=True)
class SectionCandidate:
    """One candidate concept, addressable by Stage B."""

    #: Short, sequential and assigned here: "c001". Sequential rather than
    #: content-derived so the prompt stays small and the model's references stay
    #: easy to check.
    candidate_id: str
    concept: CandidateConcept
    source: SectionSource
    #: The section-level summary, carried so Stage B can judge a candidate in the
    #: context of what its section was teaching rather than from a bare label.
    section_teaches: str

    @property
    def source_key(self) -> str:
        """Position-in-book identity of the supporting section."""
        return source_key(self.source)

    @property
    def citation(self) -> str:
        return self.source.citation()


def build_candidates(analysed: Sequence[AnalysedSection]) -> list[SectionCandidate]:
    """Flatten Stage A results into an addressable candidate list.

    Ids are assigned in reading order, so the same analyses always produce the
    same ids and a run can be compared against another.
    """
    candidates: list[SectionCandidate] = []
    for item in analysed:
        for concept in item.analysis.concepts:
            candidates.append(
                SectionCandidate(
                    candidate_id=f"c{len(candidates) + 1:03d}",
                    concept=concept,
                    source=item.source,
                    section_teaches=item.analysis.teaches,
                )
            )
    return candidates
