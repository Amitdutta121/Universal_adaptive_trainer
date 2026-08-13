"""Validate generation requests, and validate the taxonomy the model claims.

The professor chooses a section, a difficulty and a question type; the generator
reads the section and decides which topic and subtopics the question exercises.
So this module has two halves, and they run either side of the model call:

* :func:`build_question_spec` resolves the professor's request before any LLM
  call, so an unapproved curriculum or a missing section fails without spending
  a request.
* :func:`resolve_claimed_taxonomy` checks what the model came back with. Those
  ids are now model output, not professor input, and nothing downstream may
  treat them as trusted until they have been matched against the approved tree.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus, Difficulty, QuestionType
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


class ClaimedTaxonomy(BaseModel):
    """A topic and its subtopics, confirmed to exist in the approved version."""

    topic_id: int
    subtopic_ids: list[int] = Field(min_length=1)


def build_question_spec(
    session: Session,
    *,
    curriculum_version_id: int,
    question_type: QuestionType,
    difficulty: Difficulty,
    source_section_ids: list[int],
    seed: str | None = None,
) -> QuestionSpec:
    """Resolve and validate one generation request before the model runs.

    Raises:
        InvalidQuestionSpecError: the curriculum is not approved, or a source
            section is missing.
    """
    require_approved_version(session, curriculum_version_id)
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


def resolve_claimed_taxonomy(
    version: CurriculumVersionRow,
    *,
    topic_id: int,
    subtopic_ids: list[int],
) -> ClaimedTaxonomy:
    """Check the topic and subtopics a model claimed against the approved tree.

    Duplicates are dropped rather than rejected: a model naming the same
    subtopic twice has still classified the question once, and the join table
    would refuse the second row anyway.

    Raises:
        InvalidQuestionSpecError: the topic is not in this version, the subtopic
            list is empty or too long, or a subtopic does not belong to the
            claimed topic.
    """
    topic = next((row for row in version.topics if row.id == topic_id), None)
    if topic is None:
        raise InvalidQuestionSpecError(
            "The generator claimed a topic that is not in the curriculum version.",
            detail=f"Topic {topic_id} is not in approved version {version.id}.",
        )

    unique_ids: list[int] = []
    for subtopic_id in subtopic_ids:
        if subtopic_id not in unique_ids:
            unique_ids.append(subtopic_id)

    if not unique_ids:
        raise InvalidQuestionSpecError(
            "The generator claimed no subtopic.",
            detail=f"A question must name at least one subtopic of topic {topic_id}.",
        )
    if len(unique_ids) > MAX_CLAIMED_SUBTOPICS:
        raise InvalidQuestionSpecError(
            "The generator claimed too many subtopics.",
            detail=(
                f"{len(unique_ids)} subtopics claimed; at most {MAX_CLAIMED_SUBTOPICS} are allowed."
            ),
        )

    owned = {row.id for row in topic.subtopics}
    foreign = [sid for sid in unique_ids if sid not in owned]
    if foreign:
        raise InvalidQuestionSpecError(
            "Every claimed subtopic must belong to the claimed topic.",
            detail=f"Subtopic id(s) not under topic {topic_id}: {foreign}",
        )

    return ClaimedTaxonomy(topic_id=topic_id, subtopic_ids=unique_ids)
