"""Curriculum boundary.

Responsibility
    Derive a proposed Topic -> Subtopic curriculum from the professor's imported
    books, so that nobody has to hand-author a complete knowledge-component
    model, and hold it for review.

Status
    **Proposal is implemented.** Two LLM stages produce it:

    1. :mod:`app.curriculum.extraction` -- Stage A, per instructional section:
       what the section teaches and which assessable concepts it introduces.
    2. :mod:`app.curriculum.normalization` -- Stage B, across every book:
       which candidate concepts are the same skill, under one normalised name,
       with an auditable reason.

    :mod:`app.curriculum.checks` then validates the result deterministically, and
    :mod:`app.curriculum.service` writes it as a ``PROPOSED`` version.

    **Review, editing and approval are not implemented.** A proposal can be
    inspected in full but not yet approved through the UI, so question
    generation remains blocked on an approved version by design.

Key rules
    * A proposed subtopic must be something a student can practise, a professor
      can assess with several different questions, and the adaptive engine can
      track a weakness against. Terminology extraction is explicitly not the
      task; see :mod:`app.curriculum.extraction`.
    * Every subtopic is traceable to the sections it came from, keeps the
      differing book wordings that were merged into it, and states why they were
      merged. A proposal a professor cannot audit is not reviewable.
    * Stable ids come from source-declared labels and sections, never from the
      display names a professor will edit -- see :mod:`app.curriculum.stable_ids`.
    * An approved :class:`~app.domain.curriculum.CurriculumVersion` is immutable.
      Editing an approved curriculum creates a new version so that questions
      already grounded in the old version keep pointing at what they were written
      against (ADR-002).

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.llm``,
    ``app.persistence``, and ``app.ingestion.retrieval`` -- the sanctioned
    read-only surface for fetching grounding text with citations. Must not import
    ``app.generation``, ``app.adaptive`` or ``app.web``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings
from app.curriculum.service import (
    CurriculumProposalService,
    decode_json_list,
    decode_metadata,
    decode_proposal_warnings,
)
from app.llm import StructuredLLMClient

__all__ = [
    "CurriculumProposalService",
    "decode_json_list",
    "decode_metadata",
    "decode_proposal_warnings",
    "get_curriculum_proposer",
]


def get_curriculum_proposer(
    session: Session,
    client: StructuredLLMClient | None = None,
    settings: Settings | None = None,
) -> CurriculumProposalService:
    """Return the configured curriculum proposer.

    Args:
        session: the database session the proposal will read books from and be
            written to.
        client: overrides the client built from settings. The seam tests use to
            run the whole pipeline deterministically, without an API key.
        settings: overrides the process settings.

    Raises:
        ConfigurationError: if no LLM provider or credentials are configured and
            no client was supplied. Raised here, before any book is read, so an
            unconfigured run costs nothing and says exactly what is missing.
    """
    return CurriculumProposalService(session, client=client, settings=settings)
