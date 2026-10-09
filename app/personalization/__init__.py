"""Personalization boundary (professor preference learning).

Responsibility
    Turn accumulated professor feedback into the generation instruction for each
    question type, so that questions move toward what this professor approves.

Status
    What the generator is told for each question type is learned as **guidelines** in
    :mod:`app.memory` (ADR-063), not here: the per-type rule rewriter of ADR-033 was
    retired in m5. This package keeps :func:`reviews_for_type`, the reviews that count as
    evidence for one type of one subject.

Key rules
    * Input is professor feedback only. Student performance belongs to the
      separate student-adaptation loop and must not leak in here.
    * One subject's reviews are never evidence for another's (ADR-059).

Allowed dependencies
    ``app.assessment``, ``app.domain``, ``app.persistence``, ``app.subjects``.
"""

from __future__ import annotations

from app.personalization.instructions import reviews_for_type

__all__ = ["reviews_for_type"]
