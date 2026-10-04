"""Validate generation requests, and validate the taxonomy the model claims.

The professor chooses a section, a difficulty and a question type; the generator
reads the section and decides which topic and subtopics the question exercises.
So this module has two halves, and they run either side of the model call:

* :func:`build_question_spec` resolves the professor's request before any LLM
  call, so an unapproved curriculum or a missing section fails without spending
  a request.
* :func:`check_claimed_taxonomy` checks what the model came back with. Those
  ids are now model output, not professor input, and nothing downstream may
  treat them as trusted until they have been matched against the approved tree.

The second half reports rather than raises (ADR-032). A refused claim is retried
with the violation stated and the question is stored either way, so "this claim
is wrong" has to be a value that can be recorded, fed back into a prompt and
rendered -- not an exception that ends the run.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.domain.enums import ClaimViolation, CurriculumStatus, Difficulty, QuestionType
from app.errors import InvalidQuestionSpecError, NotFoundError
from app.persistence.models import CurriculumVersionRow
from app.persistence.repositories import BookStructureRepository, CurriculumRepository

#: Ceiling on how many subtopics one question may claim. A question that says it
#: exercises half the taxonomy has classified nothing, and every claimed subtopic
#: takes a share of the weakness update, so an inflated list quietly dilutes the
#: signal the adaptive engine runs on.
MAX_CLAIMED_SUBTOPICS = 3


class QuestionSpec(BaseModel):
    """One resolved generation request: what the professor asked for.

    Carries no topic or subtopic. Those are the generator's answer, not part of
    the question being put to it, and they are recorded on the produced
    :class:`~app.domain.questions.Question` instead.
    """

    curriculum_version_id: int
    question_type: QuestionType
    difficulty: Difficulty
    source_section_ids: list[int] = Field(min_length=1, max_length=1)
    seed: str | None = None
    #: Question setup rounds only (docs/QUESTION_SETUP_PLAN.md): the subtopic the question is
    #: *asked* to assess, and the library style it must be written in. ``None`` on every
    #: section-only request, which is generated exactly as before. A spec with a target is a
    #: *round spec*: the generator states the target, and the round pipeline judges it inside
    #: the retry loop and drops it on final failure instead of storing it.
    target_subtopic_id: int | None = None
    style_id: str | None = None

    @property
    def is_round_spec(self) -> bool:
        return self.target_subtopic_id is not None

    def stored(self) -> dict[str, object]:
        """The spec as frozen on the question.

        A section-only spec omits the two round fields, so questions generated outside a
        round keep exactly the ``spec_json`` they had before rounds existed.
        """
        exclude = None if self.is_round_spec else {"target_subtopic_id", "style_id"}
        return self.model_dump(mode="json", exclude=exclude)


class SubtopicOwner(BaseModel):
    """A claimed subtopic that exists, and the topic that actually owns it.

    Carried so the retry can offer the model the other way out of a cross-topic
    claim: keep the subtopic and move the topic. Naming the owner is reading the
    approved tree aloud, not guessing -- the model still decides which of the two
    it meant.
    """

    subtopic_id: int
    subtopic_name: str
    topic_id: int
    topic_name: str


class TaxonomyClaimOutcome(BaseModel):
    """What the generator claimed, whether it holds, and what of it can be stored.

    Three separate things, deliberately not collapsed into one:

    * the claim **as the model made it**, which is the evidence and never edited;
    * the **violations**, which drive the retry prompt and the deterministic check;
    * the **storable** ids, which are narrower than the claim because
      ``questions.topic_id`` and ``question_subtopics.subtopic_id`` are foreign
      keys -- an id that names nothing cannot reach a column at all.

    Storability is decided by existence, not by correctness. A cross-topic claim
    stores verbatim and is refused by the deterministic checks afterwards; only
    an id that does not exist is dropped. That keeps the stored row as close to
    what the model said as the schema permits.
    """

    claimed_topic_id: int
    claimed_subtopic_ids: list[int]
    violations: list[ClaimViolation] = Field(default_factory=list)
    #: One human sentence, reused verbatim as the retry instruction and as the
    #: validation check's detail, so the professor reads what the model was told.
    detail: str | None = None
    storable_topic_id: int | None = None
    storable_subtopic_ids: list[int] = Field(default_factory=list)
    #: Claimed subtopic ids that are the reason for refusal -- unknown ones and
    #: ones belonging to another topic. Structured rather than only described in
    #: ``detail`` so the retry can name them as the thing to change, which a
    #: sentence about them evidently does not achieve on its own.
    offending_subtopic_ids: list[int] = Field(default_factory=list)
    #: Where the cross-topic ones actually live, for the "move the topic instead"
    #: alternative. Empty unless the claim named subtopics of another topic.
    foreign_owners: list[SubtopicOwner] = Field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.violations


def build_question_spec(
    session: Session,
    *,
    curriculum_version_id: int,
    question_type: QuestionType,
    difficulty: Difficulty,
    source_section_ids: list[int],
    seed: str | None = None,
    target_subtopic_id: int | None = None,
    style_id: str | None = None,
) -> QuestionSpec:
    """Resolve and validate one generation request before the model runs.

    ``target_subtopic_id`` / ``style_id`` make it a round spec; the target must be a
    subtopic of this version.

    Raises:
        InvalidQuestionSpecError: the curriculum is not approved, a source
            section is missing, the target subtopic is not in the version, or the
            question type is not built yet.
    """
    from app.question_types import implemented_types

    if question_type not in implemented_types():
        raise InvalidQuestionSpecError(
            "This question type cannot be generated yet.",
            detail=f"{question_type.value} has no module in app/question_types.",
        )
    version = require_approved_version(session, curriculum_version_id)
    if target_subtopic_id is not None and not any(
        subtopic.id == target_subtopic_id
        for topic in version.topics
        for subtopic in topic.subtopics
    ):
        raise InvalidQuestionSpecError(
            "The target subtopic is not part of this taxonomy.",
            detail=f"Subtopic {target_subtopic_id} is not in version {curriculum_version_id}.",
        )
    structure = BookStructureRepository(session)

    for section_id in source_section_ids:
        try:
            structure.get_section(section_id)
        except NotFoundError:
            raise InvalidQuestionSpecError(
                "Every source section must exist.",
                detail=f"Section {section_id} does not exist.",
            ) from None

    try:
        return QuestionSpec(
            curriculum_version_id=curriculum_version_id,
            question_type=question_type,
            difficulty=difficulty,
            source_section_ids=source_section_ids,
            seed=seed,
            target_subtopic_id=target_subtopic_id,
            style_id=style_id,
        )
    except ValidationError as exc:
        raise InvalidQuestionSpecError(
            "A cold-start question spec needs exactly one source section.",
            detail=str(exc.errors()),
        ) from None


def require_approved_version(session: Session, curriculum_version_id: int) -> CurriculumVersionRow:
    """Return the curriculum version with its tree, or refuse if unapproved."""
    version = CurriculumRepository(session).get_with_tree(curriculum_version_id)
    status = CurriculumStatus(version.status)
    if status is not CurriculumStatus.APPROVED:
        raise InvalidQuestionSpecError(
            "Question generation requires an approved curriculum version.",
            detail=f"Version {curriculum_version_id} has status {status.value}.",
        )
    return version


def check_claimed_taxonomy(
    version: CurriculumVersionRow,
    *,
    topic_id: int,
    subtopic_ids: list[int],
) -> TaxonomyClaimOutcome:
    """Check the topic and subtopics a model claimed against the approved tree.

    Reports rather than raises (ADR-032): the caller retries a refused claim and
    stores the question either way, so every rule broken has to be nameable and
    every id has to be classified as storable or not.

    Duplicates are dropped rather than counted: a model naming the same subtopic
    twice has still classified the question once, and the join table would refuse
    the second row anyway. The claim is still reported verbatim, duplicates
    included, because that is what the model actually said.
    """
    unique_ids: list[int] = []
    for subtopic_id in subtopic_ids:
        if subtopic_id not in unique_ids:
            unique_ids.append(subtopic_id)

    topic = next((row for row in version.topics if row.id == topic_id), None)
    known_subtopics = {
        subtopic.id for candidate in version.topics for subtopic in candidate.subtopics
    }
    owned = {row.id for row in topic.subtopics} if topic is not None else set()

    violations: list[ClaimViolation] = []
    details: list[str] = []

    if topic is None:
        violations.append(ClaimViolation.UNKNOWN_TOPIC)
        details.append(f"Topic {topic_id} is not in approved version {version.id}.")

    unknown = [sid for sid in unique_ids if sid not in known_subtopics]
    if unknown:
        violations.append(ClaimViolation.UNKNOWN_SUBTOPICS)
        details.append(f"Subtopic id(s) not in this version: {unknown}.")

    if not unique_ids:
        violations.append(ClaimViolation.NO_SUBTOPIC)
        details.append(f"A question must name at least one subtopic of topic {topic_id}.")
    elif len(unique_ids) > MAX_CLAIMED_SUBTOPICS:
        violations.append(ClaimViolation.TOO_MANY_SUBTOPICS)
        details.append(
            f"{len(unique_ids)} subtopics claimed; at most {MAX_CLAIMED_SUBTOPICS} are allowed."
        )

    # Only meaningful once the topic resolves: every subtopic of a topic that does
    # not exist is "foreign", which would restate UNKNOWN_TOPIC rather than add to it.
    foreign: list[int] = []
    if topic is not None:
        foreign = [sid for sid in unique_ids if sid in known_subtopics and sid not in owned]
        if foreign:
            violations.append(ClaimViolation.FOREIGN_SUBTOPICS)
            details.append(f"Subtopic id(s) not under topic {topic_id}: {foreign}.")

    return TaxonomyClaimOutcome(
        claimed_topic_id=topic_id,
        claimed_subtopic_ids=subtopic_ids,
        violations=violations,
        detail=" ".join(details) or None,
        storable_topic_id=topic.id if topic is not None else None,
        storable_subtopic_ids=[sid for sid in unique_ids if sid in known_subtopics],
        offending_subtopic_ids=unknown + foreign,
        foreign_owners=_owners_of(version, foreign),
    )


def _owners_of(version: CurriculumVersionRow, subtopic_ids: list[int]) -> list[SubtopicOwner]:
    """Look up which topic each of ``subtopic_ids`` belongs to."""
    wanted = set(subtopic_ids)
    if not wanted:
        return []
    return [
        SubtopicOwner(
            subtopic_id=subtopic.id,
            subtopic_name=subtopic.name,
            topic_id=candidate.id,
            topic_name=candidate.name,
        )
        for candidate in version.topics
        for subtopic in candidate.subtopics
        if subtopic.id in wanted
    ]
