"""Which system prompt each judge actually runs, and what that panel is called.

The shipped prompts in :mod:`app.evaluation.prompts` are the defaults. A
professor may override any of them (ADR-038); this module is the single place
that resolves the two into the set in force, so the synchronous judges and the
bulk re-run cannot end up running different text.

**The version is a fingerprint, not a counter.** ``effective_rubric_version``
hashes the prompts actually in force. A counter cannot tell two prompt sets
apart when both have been edited the same number of times, and reverting one
judge would inherit the version of the edit it undid -- after which calibration
would pool pairs from two different panels into one agreement figure, which is
exactly the mistake ADR-035 exists to prevent. A fingerprint cannot do that:
identical prompts always produce the same name, and any change always produces a
different one.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.domain.enums import JudgeMetricId
from app.evaluation.prompts import RUBRIC_VERSION, SYSTEM_PROMPT_FOR
from app.persistence.repositories import JudgePromptRepository

#: Hex characters of the digest kept in the version name. Short enough to read in
#: a table, wide enough that two prompt sets will not collide in one bank.
_FINGERPRINT_CHARS = 8


def resolve_system_prompts(session: Session) -> dict[JudgeMetricId, str]:
    """The system prompt each judge runs now: the override, else the shipped one."""
    overrides = {row.metric: row.system_prompt for row in JudgePromptRepository(session).list_all()}
    return {metric: overrides.get(metric, SYSTEM_PROMPT_FOR[metric]) for metric in JudgeMetricId}


def effective_rubric_version(session: Session) -> str:
    """Name the panel in force, so two panels can never share a name.

    An untouched installation returns :data:`RUBRIC_VERSION` unchanged -- there is
    no edit, so claiming a modified judge would be a lie about provenance. Any
    override appends a fingerprint of all four prompts.
    """
    prompts = resolve_system_prompts(session)
    if all(prompts[metric] == SYSTEM_PROMPT_FOR[metric] for metric in JudgeMetricId):
        return RUBRIC_VERSION
    return f"{RUBRIC_VERSION}+{fingerprint(prompts)}"


def fingerprint(prompts: dict[JudgeMetricId, str]) -> str:
    """A short, stable digest of one prompt set.

    Metrics are hashed in enum order with an explicit separator, so the digest
    depends on which judge holds which text rather than on the concatenation
    alone.
    """
    digest = hashlib.sha256()
    for metric in JudgeMetricId:
        digest.update(metric.value.encode("utf-8"))
        digest.update(b"\0")
        digest.update(prompts[metric].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:_FINGERPRINT_CHARS]


def is_edited(session: Session, metric: JudgeMetricId) -> bool:
    """Whether this judge is running professor-edited text."""
    return JudgePromptRepository(session).get(metric) is not None
