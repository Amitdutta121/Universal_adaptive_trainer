"""The style library and the setup suggester (docs/QUESTION_SETUP_PLAN.md, agent A).

The library is curated code data per subject (``app/styles/<subject>.py``). The suggester
makes one structured model call over the approved taxonomy's subtopics and the library, then
validates what came back: unknown style ids are dropped, targets are clamped, and every
subtopic leaves with at least one style -- and a style for every difficulty -- chosen by fit
when the model gave none.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coverage.schema import MIN_QUESTIONS_PER_CELL
from app.domain.enums import CurriculumStatus, Difficulty
from app.errors import DomainRuleError, FeatureNotAvailableError
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import (
    BookSectionRow,
    CurriculumVersionRow,
    SubtopicEvidenceRow,
    SubtopicRow,
)
from app.persistence.repositories import CurriculumRepository
from app.styles.python import PYTHON_STYLES
from app.styles.python import SUBJECT as PYTHON_SUBJECT
from app.styles.schema import (
    MAX_CELL_TARGET,
    MIN_CELL_TARGET,
    CellTarget,
    QuestionStyle,
    SetupSuggestion,
    SubtopicStyleSuggestion,
)
from app.subjects import profile_for_version

logger = logging.getLogger(__name__)

_LIBRARIES: dict[str, list[QuestionStyle]] = {PYTHON_SUBJECT: PYTHON_STYLES}

#: Default target when the model gives none for a cell. Clamped, should the coverage minimum
#: ever leave the suggester's bounds.
DEFAULT_CELL_TARGET = max(MIN_CELL_TARGET, min(MAX_CELL_TARGET, MIN_QUESTIONS_PER_CELL))

#: Styles the model may suggest per subtopic before the rest are cut.
MAX_STYLES_PER_SUBTOPIC = 4

_FALLBACK_REASON = "Chosen by how well the style's topics match this subtopic."


def get_library(subject: str) -> list[QuestionStyle]:
    """Every style in the library of one subject, in display order.

    ``subject`` is a subject storage key (``SubjectProfile.storage_key``, e.g.
    ``intro_python``). A subject with no curated library returns ``[]`` -- never raises -- so
    the setup modal can say "no styles for this subject yet". Pure: no I/O, no model call.
    """
    return list(_LIBRARIES.get(subject, []))


# ------------------------------------------------------------------ model output


class _SubtopicDraft(BaseModel):
    """What the model returns for one subtopic. Validated and clamped afterwards."""

    subtopic_id: int
    style_ids: list[str] = Field(default_factory=list, description="Library style ids, best first.")
    reason: str = Field(default="", description="One sentence for the professor.")
    easy: int | None = Field(default=None, description="Target approved easy questions, 1-6.")
    medium: int | None = Field(default=None, description="Target approved medium questions, 1-6.")
    hard: int | None = Field(
        default=None,
        description=(
            "Target approved hard questions. 0 when the lesson cannot support a hard "
            "question, otherwise 1-6."
        ),
    )


class _SetupDraft(BaseModel):
    subtopics: list[_SubtopicDraft] = Field(default_factory=list)


SYSTEM = (
    "You plan a question bank for one course. For every subtopic of the approved taxonomy, "
    "choose the question styles from the library that fit it best (1 to "
    f"{MAX_STYLES_PER_SUBTOPIC}, best first, only ids from the library), give one short "
    "sentence the professor reads explaining why, and say how many approved questions each "
    f"difficulty of that subtopic should reach ({MIN_CELL_TARGET} to {MAX_CELL_TARGET}; "
    f"{DEFAULT_CELL_TARGET} is the usual amount, more for central subtopics, fewer for minor "
    "ones). When a subtopic has lesson text, set hard to 0 if that text teaches only one "
    "idea and cannot support a hard question, and set hard from 1 to 6 when the text contains "
    "several ideas that can be composed. When no lesson text is attached, choose a hard target "
    "from 1 to 6 as usual. Do not choose a style for a difficulty whose target is 0. Between "
    "them the chosen styles should cover every difficulty whose target is above 0. Styles "
    "checked by running hidden tests cannot read or write files: do not choose them for file "
    "input/output subtopics."
)


def _target_value(draft: _SubtopicDraft | None, difficulty: Difficulty) -> int:
    """Easy and medium stay at least 1. A hard 0 stays 0. A missing number is the default."""
    raw = getattr(draft, difficulty.value) if draft else None
    if raw is None:
        return DEFAULT_CELL_TARGET
    floor = 0 if difficulty is Difficulty.HARD else MIN_CELL_TARGET
    return max(floor, min(MAX_CELL_TARGET, raw))


_WORD = re.compile(r"[a-z]+")


def _words(text: str) -> set[str]:
    # Crude stemming ("loops" ~ "loop") is enough for ranking a fallback.
    return {word.rstrip("s") for word in _WORD.findall(text.lower()) if len(word) > 2}


def _rank_by_fit(styles: list[QuestionStyle], subtopic: SubtopicRow) -> list[QuestionStyle]:
    """Styles ordered by how many of their ``applies_to`` words the subtopic mentions.

    Ties keep library order, so with no overlap at all the first library style comes first.
    """
    text = " ".join(
        part or ""
        for part in (
            subtopic.name,
            subtopic.description,
            subtopic.topic.name if subtopic.topic else "",
        )
    )
    target = _words(text)

    def overlap(style: QuestionStyle) -> int:
        return len(target & _words(" ".join(style.applies_to)))

    return sorted(styles, key=overlap, reverse=True)  # sorted is stable


def _validated(
    subtopic: SubtopicRow,
    draft: _SubtopicDraft | None,
    library: dict[str, QuestionStyle],
) -> tuple[SubtopicStyleSuggestion, list[CellTarget]]:
    chosen: list[str] = []
    for style_id in draft.style_ids if draft else []:
        if style_id in library and style_id not in chosen:
            chosen.append(style_id)
        elif style_id not in library:
            logger.info("Suggester named unknown style %r for subtopic %s.", style_id, subtopic.id)
    chosen = chosen[:MAX_STYLES_PER_SUBTOPIC]
    reason = (draft.reason.strip() if draft else "") or _FALLBACK_REASON

    ranked = _rank_by_fit(list(library.values()), subtopic)
    if not chosen:
        chosen.append(ranked[0].id)
        reason = _FALLBACK_REASON
    targets = [
        CellTarget(
            subtopic_id=subtopic.id,
            difficulty=difficulty,
            target=_target_value(draft, difficulty),
        )
        for difficulty in Difficulty
    ]
    # A cell with a target needs a style that can be written at its difficulty.
    # A hard target of 0 does not get a hard style added back.
    for cell in targets:
        if cell.target == 0:
            continue
        if not any(cell.difficulty in library[style_id].difficulty_range for style_id in chosen):
            fit = next((s for s in ranked if cell.difficulty in s.difficulty_range), None)
            if fit is not None:
                chosen.append(fit.id)
    return SubtopicStyleSuggestion(
        subtopic_id=subtopic.id, style_ids=chosen, reason=reason
    ), targets


def _lesson_excerpts(session: Session, subtopic_ids: list[int]) -> dict[int, str]:
    """The first evidence section's text for each subtopic, when one is linked."""
    if not subtopic_ids:
        return {}
    rows = session.execute(
        select(SubtopicEvidenceRow.subtopic_id, BookSectionRow.text)
        .join(BookSectionRow, BookSectionRow.id == SubtopicEvidenceRow.section_id)
        .where(SubtopicEvidenceRow.subtopic_id.in_(subtopic_ids))
        .order_by(SubtopicEvidenceRow.id)
    ).all()
    excerpts: dict[int, str] = {}
    for subtopic_id, text in rows:
        if subtopic_id in excerpts:
            continue
        cleaned = (text or "").strip()
        if cleaned:
            excerpts[subtopic_id] = cleaned[:2000]
    return excerpts


def _prompt(
    version: CurriculumVersionRow, styles: list[QuestionStyle], lessons: dict[int, str]
) -> str:
    library = [
        {
            "id": style.id,
            "name": style.name,
            "summary": style.summary,
            "question_type": style.question_type.value,
            "difficulties": [difficulty.value for difficulty in style.difficulty_range],
            "checked_by": style.checked_by,
            "fits": style.applies_to,
        }
        for style in styles
    ]
    taxonomy = [
        {
            "topic": topic.name,
            "subtopics": [
                {
                    "id": subtopic.id,
                    "name": subtopic.name,
                    "description": subtopic.description,
                    "lesson": lessons.get(subtopic.id, ""),
                }
                for subtopic in topic.subtopics
            ],
        }
        for topic in version.topics
    ]
    return (
        f"Style library ({len(styles)} styles):\n{json.dumps(library, indent=1)}\n\n"
        f"Approved taxonomy '{version.label}':\n{json.dumps(taxonomy, indent=1)}\n\n"
        "Return one entry per subtopic id."
    )


def suggest_setup(
    session: Session,
    curriculum_version_id: int,
    *,
    client: StructuredLLMClient | None = None,
) -> SetupSuggestion:
    """Suggest library styles per subtopic and a target per cell for one approved taxonomy.

    One structured model call over (subtopics x the subject's library). Every returned style id
    is validated against :func:`get_library` (narrowed to the course's question types); unknown
    ids are dropped, not passed through. Every visible subtopic of the version appears in
    ``subtopics`` with at least one style -- picked by fit when the model gave none -- and
    styles covering every difficulty whose target is above 0. A hard target of 0 is kept,
    and no hard style is added back for it. Easy and medium stay at least 1. Every
    subtopic x difficulty cell gets one :class:`CellTarget` (default
    ``MIN_QUESTIONS_PER_CELL``). When a subtopic has linked lesson text, that text is in
    the prompt. Persists nothing.

    Raises:
        NotFoundError: the curriculum version does not exist.
        DomainRuleError: the version is not approved, or has no subtopics.
        FeatureNotAvailableError: the subject has no style library (for the course's types).
        LLMRequestError / MalformedModelOutputError: the model call failed.
    """
    version = CurriculumRepository(session).get_with_tree(curriculum_version_id)
    if CurriculumStatus(version.status) is not CurriculumStatus.APPROVED:
        raise DomainRuleError(
            "Question setup needs an approved taxonomy.",
            detail=f"Version {curriculum_version_id} has status {version.status}.",
        )
    subtopics = [subtopic for topic in version.topics for subtopic in topic.subtopics]
    if not subtopics:
        raise DomainRuleError("This taxonomy has no subtopics to set up questions for.")

    profile = profile_for_version(session, curriculum_version_id)
    styles = [
        style
        for style in get_library(profile.storage_key)
        if not profile.question_types or style.question_type.value in profile.question_types
    ]
    if not styles:
        raise FeatureNotAvailableError(
            "There is no question style library for this subject yet.",
            detail=f"Subject {profile.storage_key}.",
        )

    llm = client or get_structured_client()
    lessons = _lesson_excerpts(session, [subtopic.id for subtopic in subtopics])
    draft = llm.complete_structured(
        system=SYSTEM,
        prompt=_prompt(version, styles, lessons),
        response_model=_SetupDraft,
    )
    by_subtopic: dict[int, _SubtopicDraft] = {}
    for entry in draft.subtopics:
        by_subtopic.setdefault(entry.subtopic_id, entry)  # first answer wins; unknown ids ignored

    library = {style.id: style for style in styles}
    suggestions: list[SubtopicStyleSuggestion] = []
    cell_targets: list[CellTarget] = []
    for subtopic in subtopics:
        suggestion, targets = _validated(subtopic, by_subtopic.get(subtopic.id), library)
        suggestions.append(suggestion)
        cell_targets.extend(targets)

    missing = len(subtopics) - sum(1 for s in subtopics if s.id in by_subtopic)
    if missing:
        logger.info("Suggester skipped %s of %s subtopics; filled by fit.", missing, len(subtopics))
    return SetupSuggestion(
        curriculum_version_id=curriculum_version_id,
        subject=profile.storage_key,
        subtopics=suggestions,
        cell_targets=cell_targets,
    )
