"""Personalization boundary (professor preference learning).

Responsibility
    Turn accumulated professor feedback into the generation instruction for each
    question type, so that questions move toward what this professor approves.

Status
    Implemented as **per-type learned instructions** (ADR-033):
    :func:`~app.personalization.instructions.refresh_type_instruction` turns the
    reviews of one question type into a rule list, renders it into the
    type-specific slot of the generation prompt, and stores it on
    ``type_instructions``. There is no separate personalized generator: every
    question is generated with whatever has been learned for its type.

    The previous design -- a preference profile plus retrieved review examples,
    appended as a block after the prompt -- was removed. ADR-033 records why.

Key rules
    * Input is professor feedback only. Student performance belongs to the
      separate student-adaptation loop and must not leak in here.
    * A type nobody has reviewed keeps the shipped instruction. Personalization
      that invents rules from no evidence is not personalization.
    * Rules accumulate and are edited; the instruction is never rewritten from
      scratch, because that loses rules earned in earlier rounds.

Allowed dependencies
    ``app.config``, ``app.domain``, ``app.errors``, ``app.feedback``,
    ``app.generation`` (for the shipped type instruction), ``app.llm``,
    ``app.persistence``.
"""

from __future__ import annotations

from app.personalization.instructions import (
    LearnedRule,
    LearnedRules,
    refresh_type_instruction,
    render_instruction,
    reviews_for_type,
)

__all__ = [
    "LearnedRule",
    "LearnedRules",
    "refresh_type_instruction",
    "render_instruction",
    "reviews_for_type",
]
