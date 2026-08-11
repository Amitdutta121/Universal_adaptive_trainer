"""Deterministic structural checks on a proposed curriculum.

These run after Stage B and before a single row is written, and they never
consult a model. The pattern is ingestion's (ADR-015): validate totally, reject
in full, write nothing on failure -- so every curriculum version in the database
is one that passed every check.

Why these particular checks
    Each corresponds to something that silently breaks a downstream guarantee:

    * an empty name is unreviewable and unusable as a UI label;
    * a duplicate stable id makes two distinct skills share one weakness
      dimension in the adaptive engine;
    * a duplicate name inside a topic splits one skill across two dimensions;
    * a subtopic whose parent is missing, or whose parent is not the topic it
      sits under, breaks the Topic -> Subtopic grounding question generation
      requires (ADR-002);
    * a subtopic with no supporting section is an assertion the professor cannot
      check, which is the one thing curriculum proposal exists to avoid;
    * a topic with no subtopics has nothing to generate against.

Most of these should be unreachable after :mod:`app.curriculum.normalization`
does its work. That is the point: the check is the proof, not the hope.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from app.curriculum.draft import CurriculumDraft, DraftSubtopic
from app.errors import CurriculumProposalError


class DefectCode(StrEnum):
    """What went structurally wrong with a proposal."""

    EMPTY_NAME = "empty_name"
    DUPLICATE_STABLE_ID = "duplicate_stable_id"
    DUPLICATE_NAME = "duplicate_name"
    ORPHANED_SUBTOPIC = "orphaned_subtopic"
    MISSING_TOPIC_PARENT = "missing_topic_parent"
    MISSING_SOURCE_MAPPING = "missing_source_mapping"
    EMPTY_TOPIC = "empty_topic"
    NO_TOPICS = "no_topics"


@dataclass(frozen=True)
class DraftDefect:
    """One structural problem, named precisely enough to act on."""

    code: DefectCode
    message: str

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


def check_draft(draft: CurriculumDraft) -> list[DraftDefect]:
    """Return every structural defect in ``draft``. Empty means sound.

    Returns all defects rather than the first, so a broken proposal can be
    diagnosed in one pass instead of one fix at a time.
    """
    defects: list[DraftDefect] = []

    if not draft.topics:
        defects.append(DraftDefect(DefectCode.NO_TOPICS, "The proposal contains no topics at all."))

    topic_ids = {topic.stable_id for topic in draft.topics}
    defects.extend(_check_duplicates(draft))

    for topic in draft.topics:
        if not topic.name.strip():
            defects.append(
                DraftDefect(DefectCode.EMPTY_NAME, f"Topic {topic.stable_id} has a blank name.")
            )
        if not topic.subtopics:
            defects.append(
                DraftDefect(
                    DefectCode.EMPTY_TOPIC,
                    f"Topic {topic.name!r} ({topic.stable_id}) has no subtopics.",
                )
            )

        for subtopic in topic.subtopics:
            defects.extend(_check_subtopic(topic_name=topic.name, subtopic=subtopic))
            if subtopic.topic_stable_id != topic.stable_id:
                defects.append(
                    DraftDefect(
                        DefectCode.ORPHANED_SUBTOPIC,
                        f"Subtopic {subtopic.name!r} sits under topic {topic.stable_id} "
                        f"but claims parent {subtopic.topic_stable_id}.",
                    )
                )
            elif subtopic.topic_stable_id not in topic_ids:  # pragma: no cover - defensive
                defects.append(
                    DraftDefect(
                        DefectCode.MISSING_TOPIC_PARENT,
                        f"Subtopic {subtopic.name!r} names a parent topic that is not "
                        f"in this proposal: {subtopic.topic_stable_id}.",
                    )
                )

    return defects


def _check_subtopic(*, topic_name: str, subtopic: DraftSubtopic) -> list[DraftDefect]:
    """Checks that apply to one subtopic in isolation."""
    defects: list[DraftDefect] = []

    if not subtopic.name.strip():
        defects.append(
            DraftDefect(
                DefectCode.EMPTY_NAME,
                f"A subtopic of {topic_name!r} has a blank name ({subtopic.stable_id}).",
            )
        )
    if not subtopic.evidence:
        defects.append(
            DraftDefect(
                DefectCode.MISSING_SOURCE_MAPPING,
                f"Subtopic {subtopic.name!r} has no supporting sections, so nothing "
                "grounds it in the uploaded books.",
            )
        )
    for evidence in subtopic.evidence:
        if evidence.source.section_id <= 0 or evidence.source.book_id <= 0:
            defects.append(
                DraftDefect(
                    DefectCode.MISSING_SOURCE_MAPPING,
                    f"Subtopic {subtopic.name!r} cites a section that has no database "
                    f"identity (book {evidence.source.book_id}, "
                    f"section {evidence.source.section_id}).",
                )
            )
    return defects


def _check_duplicates(draft: CurriculumDraft) -> list[DraftDefect]:
    """Identifier and name collisions, across the whole proposal."""
    defects: list[DraftDefect] = []

    for label, counts in (
        ("Topic", Counter(topic.stable_id for topic in draft.topics)),
        ("Subtopic", Counter(subtopic.stable_id for subtopic in draft.subtopics)),
    ):
        for stable_id, count in sorted(counts.items()):
            if count > 1:
                defects.append(
                    DraftDefect(
                        DefectCode.DUPLICATE_STABLE_ID,
                        f"{label} identifier {stable_id} is used by {count} items.",
                    )
                )

    topic_names = Counter(topic.name.strip().casefold() for topic in draft.topics)
    for name, count in sorted(topic_names.items()):
        if count > 1:
            defects.append(
                DraftDefect(DefectCode.DUPLICATE_NAME, f"{count} topics share the name {name!r}.")
            )

    for topic in draft.topics:
        names = Counter(subtopic.name.strip().casefold() for subtopic in topic.subtopics)
        for name, count in sorted(names.items()):
            if count > 1:
                defects.append(
                    DraftDefect(
                        DefectCode.DUPLICATE_NAME,
                        f"Topic {topic.name!r} has {count} subtopics named {name!r}.",
                    )
                )

    return defects


def require_sound_draft(draft: CurriculumDraft) -> None:
    """Raise unless ``draft`` passes every check.

    Raises:
        CurriculumProposalError: naming every defect found. The proposal is
            discarded whole rather than partly written, so a professor is never
            shown a curriculum that half survived its own validation.
    """
    defects = check_draft(draft)
    if not defects:
        return
    raise CurriculumProposalError(
        "The proposed curriculum failed its structural checks and was discarded.",
        detail="; ".join(str(defect) for defect in defects[:8]),
    )
