"""Stage B: consolidating candidate concepts across books into one vocabulary.

Three textbooks teaching the same skill will name it three ways -- "Accessing
characters", "String indexing", "Selecting individual characters". Left alone,
each becomes its own subtopic, and the adaptive engine ends up tracking three
weakness dimensions for one skill, each with a third of the evidence. This stage
decides which candidates are the same concept and gives that concept one name.

What the model decides, and what this module decides
    The model decides *semantic equivalence* -- which wordings mean the same
    thing, what to call the result, and why. Everything after that is
    deterministic and lives here: checking that the ids it returned are ids that
    were actually sent, merging groups that normalised to the same name,
    assigning stable identifiers, ordering, and attaching evidence. The split
    matters because the model's judgement is unrepeatable and the bookkeeping
    must not be.

Nothing is quietly dropped
    A candidate the model failed to place is reported as a warning on the
    proposal, not discarded in silence. An id the model invented, or assigned
    twice, is a malformed response and fails the run: those are not judgement
    calls, they are the answer failing to refer to the question.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence

from app.config import Settings, get_settings
from app.curriculum.candidates import SectionCandidate
from app.curriculum.draft import (
    CurriculumDraft,
    DraftEvidence,
    DraftSubtopic,
    DraftTopic,
    ExtractionMetadata,
    ProposalWarning,
    ProposalWarningCode,
    describe_topic,
)
from app.curriculum.schema import (
    ConceptGroup,
    NormalizationResult,
    json_schema_for,
    parse_structured,
)
from app.curriculum.stable_ids import normalize_label, subtopic_stable_id, topic_stable_id
from app.errors import MalformedModelOutputError
from app.llm import StructuredLLMClient

logger = logging.getLogger(__name__)

SCHEMA_NAME = "record_normalized_concepts"
SCHEMA_DESCRIPTION = (
    "Consolidate candidate concepts collected from several textbooks into one "
    "Topic -> Subtopic vocabulary."
)

#: Definitions are shortened in the Stage B prompt: the model needs enough to
#: judge equivalence, not the whole analysis of every section in every book.
_DEFINITION_BUDGET = 240

SYSTEM_PROMPT = """\
You are building the Topic -> Subtopic curriculum for an introductory Python \
course.

You are given candidate concepts extracted from several textbooks. Different \
books describe the same skill differently. Your job is to decide which \
candidates are the SAME instructional concept and to give each concept one \
normalised name.

For example, "Accessing characters", "String indexing" and "Selecting \
individual characters" all teach retrieving a character from a string by \
position, so they form one group: topic "Strings", subtopic "Indexing".

Rules:
  * Every candidate id you were given must appear in exactly one group. Do not \
invent ids, do not repeat an id, and do not leave one out.
  * Group by what is TAUGHT, not by wording. Two identical labels teaching \
different skills belong in different groups; two different labels teaching the \
same skill belong in one.
  * A group may contain a single candidate. Do not force unrelated concepts \
together to reduce the number of groups.
  * normalized_topic is the broader area a professor would recognise, e.g. \
"Strings", "Loops", "Functions", "Dictionaries". Reuse the same topic name \
across groups that belong to the same area; spell it identically each time.
  * normalized_subtopic names one assessable skill within that topic. It must \
stay something a student can practise and be assessed on separately - not a \
single language detail, and not a whole chapter's worth of material.
  * normalized_description says what a student who has mastered the subtopic \
can do.
  * reason_for_grouping is one concise sentence stating what the grouped \
candidates have in common, specific enough that a professor can check it. \
Write "Both sections teach retrieving individual characters from strings using \
indices", not "These are similar".
  * confidence reflects how sure you are the grouping is correct.
"""


class CrossBookNormalizer:
    """Runs Stage B over every candidate gathered from every book."""

    def __init__(self, client: StructuredLLMClient, settings: Settings | None = None) -> None:
        self._client = client
        self._settings = settings or get_settings()

    def normalize(self, candidates: Sequence[SectionCandidate]) -> NormalizationResult:
        """Ask the model to consolidate ``candidates``.

        Raises:
            MalformedModelOutputError: if the response did not satisfy the schema.
            LLMRequestError: if the provider could not be reached.
        """
        if not candidates:
            raise MalformedModelOutputError(
                "Cannot normalise an empty candidate set.",
                detail="Stage A produced no candidate concepts.",
            )
        payload = self._client.complete_structured(
            system=SYSTEM_PROMPT,
            prompt=build_normalization_prompt(candidates),
            schema_name=SCHEMA_NAME,
            schema_description=SCHEMA_DESCRIPTION,
            json_schema=json_schema_for(NormalizationResult),
        )
        result = parse_structured(NormalizationResult, payload, stage="normalization")
        logger.debug(
            "Normalised %d candidate(s) into %d group(s)", len(candidates), len(result.groups)
        )
        return result


def build_normalization_prompt(candidates: Sequence[SectionCandidate]) -> str:
    """Render the candidate set as a compact, id-addressable listing."""
    lines = [
        "Candidate concepts extracted from the uploaded textbooks:",
        "",
    ]
    for candidate in candidates:
        definition = candidate.concept.definition
        if len(definition) > _DEFINITION_BUDGET:
            definition = definition[:_DEFINITION_BUDGET] + "..."
        lines.append(
            f"{candidate.candidate_id} | book: {candidate.source.book_title}"
            f" | section: {candidate.source.section_label or 'untitled'}"
            f" | label: {candidate.concept.label}"
            f" | book's topic: {candidate.concept.topic_label}"
            f" | teaches: {definition}"
        )
    lines.extend(
        (
            "",
            f"Group all {len(candidates)} candidate(s). Every id above must appear "
            "in exactly one group.",
        )
    )
    return "\n".join(lines)


def _resolve_members(
    groups: Sequence[ConceptGroup], by_id: dict[str, SectionCandidate]
) -> list[tuple[ConceptGroup, list[SectionCandidate]]]:
    """Bind each group to real candidates, refusing a response that misreferences.

    Raises:
        MalformedModelOutputError: on an id that was never sent, or one placed in
            two groups. Both mean the answer does not refer to the question that
            was asked, which is not something to repair by guessing.
    """
    claimed: dict[str, int] = {}
    resolved: list[tuple[ConceptGroup, list[SectionCandidate]]] = []

    for index, group in enumerate(groups):
        members: list[SectionCandidate] = []
        for candidate_id in group.candidate_ids:
            candidate = by_id.get(candidate_id)
            if candidate is None:
                raise MalformedModelOutputError(
                    "The model referred to a candidate concept that does not exist.",
                    detail=(
                        f"Group {group.normalized_subtopic!r} cited {candidate_id!r}, "
                        f"which was not among the {len(by_id)} candidate(s) sent."
                    ),
                )
            if candidate_id in claimed:
                raise MalformedModelOutputError(
                    "The model placed one candidate concept in two groups.",
                    detail=(
                        f"{candidate_id!r} appears in group {claimed[candidate_id]} and "
                        f"group {index}."
                    ),
                )
            claimed[candidate_id] = index
            members.append(candidate)
        resolved.append((group, members))

    return resolved


def _merge_equivalent_groups(
    resolved: Sequence[tuple[ConceptGroup, list[SectionCandidate]]],
) -> tuple[list[tuple[ConceptGroup, list[SectionCandidate]]], int]:
    """Fold together groups that normalised to the same topic and subtopic name.

    A model asked for consistent naming will still occasionally emit "String
    indexing" twice. Two subtopics with the same name under the same topic would
    split one weakness dimension in half, so they are merged here rather than
    left for the professor to notice.
    """
    merged: dict[tuple[str, str], tuple[ConceptGroup, list[SectionCandidate]]] = {}
    order: list[tuple[str, str]] = []
    duplicates = 0

    for group, members in resolved:
        key = (normalize_label(group.normalized_topic), normalize_label(group.normalized_subtopic))
        existing = merged.get(key)
        if existing is None:
            merged[key] = (group, list(members))
            order.append(key)
            continue
        duplicates += 1
        first_group, first_members = existing
        combined = ConceptGroup(
            normalized_topic=first_group.normalized_topic,
            normalized_subtopic=first_group.normalized_subtopic,
            normalized_description=first_group.normalized_description,
            # Both rationales are kept: the professor is reviewing one merged
            # subtopic and is entitled to every reason it exists.
            reason_for_grouping=_join_reasons(
                first_group.reason_for_grouping, group.reason_for_grouping
            ),
            # The weaker of the two confidences wins: a merge is only as sound as
            # its least sound half.
            confidence=min(
                first_group.confidence,
                group.confidence,
                key=_CONFIDENCE_ORDER.__getitem__,
            ),
            candidate_ids=[*first_group.candidate_ids, *group.candidate_ids],
        )
        merged[key] = (combined, [*first_members, *members])

    return [merged[key] for key in order], duplicates


#: Lower is weaker. Used to pick the more cautious of two confidences on a merge.
_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def _join_reasons(first: str, second: str) -> str:
    if normalize_label(first) == normalize_label(second):
        return first
    return f"{first.rstrip('.')}. Also merged: {second}"


def _preferred_spelling(values: Sequence[str]) -> str:
    """The most frequent spelling of a label, ties broken alphabetically."""
    counts = Counter(values)
    return min(counts, key=lambda value: (-counts[value], value))


def assemble_draft(
    candidates: Sequence[SectionCandidate],
    result: NormalizationResult,
    *,
    label: str,
    source_book_ids: Sequence[int],
    metadata: ExtractionMetadata,
    warnings: Sequence[ProposalWarning] = (),
) -> CurriculumDraft:
    """Turn Stage B's answer into a fully formed, ordered draft.

    Everything here is deterministic: the same candidates and the same response
    always produce the same draft, including identifiers and ordering.
    """
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    resolved = _resolve_members(result.groups, by_id)
    grouped, duplicates_merged = _merge_equivalent_groups(resolved)

    collected: list[ProposalWarning] = list(warnings)
    if duplicates_merged:
        collected.append(
            ProposalWarning(
                code=ProposalWarningCode.DUPLICATE_GROUPS_MERGED,
                message=(
                    f"{duplicates_merged} group(s) normalised to a name another group "
                    "already used and were merged."
                ),
            )
        )

    assigned = {member.candidate_id for _, members in grouped for member in members}
    unassigned = [candidate for candidate in candidates if candidate.candidate_id not in assigned]
    if unassigned:
        collected.append(
            ProposalWarning(
                code=ProposalWarningCode.CANDIDATES_UNASSIGNED,
                message=(
                    f"{len(unassigned)} candidate concept(s) were not placed in any group "
                    "and are absent from this proposal."
                ),
                location="; ".join(
                    f"{candidate.concept.label} ({candidate.citation})"
                    for candidate in unassigned[:5]
                ),
            )
        )

    topics = _build_topics(grouped)
    return CurriculumDraft(
        label=label,
        source_book_ids=list(source_book_ids),
        topics=topics,
        metadata=metadata,
        warnings=collected,
    )


def _build_topics(
    grouped: Sequence[tuple[ConceptGroup, list[SectionCandidate]]],
) -> list[DraftTopic]:
    """Group the consolidated concepts under their topics and order everything."""
    by_topic: dict[str, list[tuple[ConceptGroup, list[SectionCandidate]]]] = {}
    for group, members in grouped:
        by_topic.setdefault(normalize_label(group.normalized_topic), []).append((group, members))

    topics: list[DraftTopic] = []
    for entries in by_topic.values():
        topic_name = _preferred_spelling([group.normalized_topic for group, _ in entries])
        # Identity comes from the books' own topic labels, never from the
        # normalised display name the professor may rewrite.
        stable = topic_stable_id(
            member.concept.topic_label for _, members in entries for member in members
        )
        subtopics = [
            _build_subtopic(group, members, topic_stable=stable) for group, members in entries
        ]
        # Best-supported skills first: the professor reviews the load-bearing
        # parts of the proposal before the marginal ones.
        subtopics.sort(key=lambda item: (-item.section_count, item.name))
        for position, subtopic in enumerate(subtopics):
            subtopic.position = position
        topics.append(
            DraftTopic(
                stable_id=stable,
                name=topic_name,
                description=describe_topic(topic_name, subtopics),
                subtopics=subtopics,
            )
        )

    topics.sort(key=lambda item: (-len(item.subtopics), item.name))
    for position, topic in enumerate(topics):
        topic.position = position
    return topics


def _build_subtopic(
    group: ConceptGroup, members: Sequence[SectionCandidate], *, topic_stable: str
) -> DraftSubtopic:
    """Build one subtopic, carrying every wording and section behind it."""
    ordered = sorted(members, key=lambda item: (item.source.book_id, item.source.section_id))
    candidate_labels = list(dict.fromkeys(member.concept.label for member in ordered))
    return DraftSubtopic(
        stable_id=subtopic_stable_id(
            candidate_labels=candidate_labels,
            candidate_topic_labels=[member.concept.topic_label for member in ordered],
            source_keys=[member.source_key for member in ordered],
        ),
        topic_stable_id=topic_stable,
        name=group.normalized_subtopic,
        description=group.normalized_description,
        reason_for_grouping=group.reason_for_grouping,
        confidence=group.confidence,
        candidate_labels=candidate_labels,
        evidence=[
            DraftEvidence(
                candidate_label=member.concept.label,
                definition=member.concept.definition,
                quotes=list(member.concept.evidence),
                source=member.source,
            )
            for member in ordered
        ],
    )
