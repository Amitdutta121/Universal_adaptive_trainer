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

**Overrides are per subject.** A judge edited for one subject preset never
judges another subject's questions; every function here takes ``subject``,
defaulting to the legacy subject that every pre-existing override belongs to.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.domain.enums import JudgeMetricId
from app.evaluation.prompts import rubric_version_for, system_prompts_for
from app.persistence.repositories import JudgePromptRepository
from app.subjects import PYTHON_PROFILE, SubjectProfile

#: Hex characters of the digest kept in the version name. Short enough to read in
#: a table, wide enough that two prompt sets will not collide in one bank.
_FINGERPRINT_CHARS = 8


def resolve_system_prompts(
    session: Session, *, profile: SubjectProfile = PYTHON_PROFILE
) -> dict[JudgeMetricId, str]:
    """The system prompt each judge runs for this subject: its override, else the shipped one."""
    shipped = system_prompts_for(profile)
    overrides = {
        row.metric: row.system_prompt
        for row in JudgePromptRepository(session).list_all(subject=profile.storage_key)
    }
    return {metric: overrides.get(metric, shipped[metric]) for metric in JudgeMetricId}


def effective_rubric_version(session: Session, *, profile: SubjectProfile = PYTHON_PROFILE) -> str:
    """Name the panel in force, so two panels can never share a name.

    An untouched Intro Python installation returns :data:`RUBRIC_VERSION` unchanged -- there is
    no edit, so claiming a modified judge would be a lie about provenance. Another subject's
    shipped panel is named by :func:`rubric_version_for`; any override appends a fingerprint of
    all four prompts.
    """
    prompts = resolve_system_prompts(session, profile=profile)
    base = rubric_version_for(profile)
    if prompts == system_prompts_for(profile):
        return base
    return f"{base}+{fingerprint(prompts)}"


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


def is_edited(
    session: Session, metric: JudgeMetricId, *, profile: SubjectProfile = PYTHON_PROFILE
) -> bool:
    """Whether this judge is running professor-edited text for this subject."""
    return JudgePromptRepository(session).get(metric, subject=profile.storage_key) is not None
