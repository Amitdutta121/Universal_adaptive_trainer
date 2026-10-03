"""Question setup: the style library, the AI-suggested setup, and saving it.

docs/QUESTION_SETUP_PLAN.md (agent A). Saving a setup starts round 1 in the background
(``app.generation.rounds.start_round`` then ``run_round``) and returns at once -- the ``/api/*``
proxy would time out on a synchronous round.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.domain.enums import CurriculumStatus
from app.errors import DomainRuleError
from app.generation import rounds
from app.llm import StructuredLLMClient
from app.persistence.models import CurriculumVersionRow, QuestionSetupRow
from app.persistence.repositories import (
    CurriculumRepository,
    GenerationRoundRepository,
    QuestionSetupRepository,
)
from app.styles import get_library, suggest_setup
from app.subjects import profile_for_version
from app.web.routes.api.deps import CourseProfile, CourseScope, DbSession, ensure_in_course
from app.web.routes.api.schemas import (
    CurrentSetupResponse,
    QuestionSetupOut,
    SaveSetupRequest,
    SaveSetupResponse,
    SetupSuggestionResponse,
    StyleListResponse,
    SuggestSetupRequest,
)

router = APIRouter(tags=["question-setup"])


def get_setup_client() -> StructuredLLMClient | None:
    """The structured client the suggester runs on. ``None`` lets it build its own from
    settings; tests override this with a fake."""
    return None


SetupClientDep = Annotated[StructuredLLMClient | None, Depends(get_setup_client)]


@router.get("/styles", response_model=StyleListResponse)
def list_styles(profile: CourseProfile, subject: str | None = None) -> StyleListResponse:
    """The style library of ``subject``, or of the course's subject when omitted."""
    key = subject or profile.storage_key
    return StyleListResponse(subject=key, styles=get_library(key))


@router.post("/setup/suggest", response_model=SetupSuggestionResponse)
def suggest(
    session: DbSession, course: CourseScope, body: SuggestSetupRequest, client: SetupClientDep
) -> SetupSuggestionResponse:
    """AI-suggested styles per subtopic and a target per cell. Persists nothing."""
    version = CurriculumRepository(session).get_with_tree(body.curriculum_version_id)
    ensure_in_course(version.course_id, course, f"Curriculum version {version.id}")
    return suggest_setup(session, body.curriculum_version_id, client=client)


@router.get("/setup", response_model=CurrentSetupResponse)
def current_setup(
    session: DbSession, course: CourseScope, curriculum_version_id: int
) -> CurrentSetupResponse:
    """The newest saved setup of a taxonomy, with its newest round; ``setup`` is null if none."""
    version = CurriculumRepository(session).get_with_tree(curriculum_version_id)
    ensure_in_course(version.course_id, course, f"Curriculum version {version.id}")
    row = QuestionSetupRepository(session).current(curriculum_version_id)
    if row is None:
        return CurrentSetupResponse(setup=None)
    latest = GenerationRoundRepository(session).latest(row.id)
    return CurrentSetupResponse(setup=QuestionSetupOut.from_row(row, latest_round=latest))


def _validate(session: Session, version: CurriculumVersionRow, body: SaveSetupRequest) -> None:
    """Refuse a setup that names subtopics outside the taxonomy or styles outside the library."""
    if CurriculumStatus(version.status) is not CurriculumStatus.APPROVED:
        raise DomainRuleError(
            "Question setup needs an approved taxonomy.",
            detail=f"Version {version.id} has status {version.status}.",
        )
    subtopic_ids = {s.id for topic in version.topics for s in topic.subtopics}
    library = {
        style.id for style in get_library(profile_for_version(session, version.id).storage_key)
    }

    named = {entry.subtopic_id for entry in body.approved_styles} | {
        cell.subtopic_id for cell in body.cell_targets
    }
    foreign = sorted(named - subtopic_ids)
    if foreign:
        raise DomainRuleError(
            "The setup names subtopics that are not in this taxonomy.",
            detail=f"Unknown subtopic ids: {', '.join(map(str, foreign))}.",
        )
    unknown = sorted(
        {style_id for entry in body.approved_styles for style_id in entry.style_ids} - library
    )
    if unknown:
        raise DomainRuleError(
            "The setup names styles that are not in this subject's library.",
            detail=f"Unknown style ids: {', '.join(unknown)}.",
        )
    if not any(entry.style_ids for entry in body.approved_styles):
        raise DomainRuleError("Approve at least one style before starting generation.")
    cells = [(cell.subtopic_id, cell.difficulty) for cell in body.cell_targets]
    if len(cells) != len(set(cells)):
        raise DomainRuleError("The setup lists the same subtopic and difficulty twice.")


@router.post("/setup", response_model=SaveSetupResponse, status_code=status.HTTP_201_CREATED)
def save_setup(
    session: DbSession, course: CourseScope, body: SaveSetupRequest, background: BackgroundTasks
) -> SaveSetupResponse:
    """Save the approved setup and start round 1 in the background."""
    version = CurriculumRepository(session).get_with_tree(body.curriculum_version_id)
    ensure_in_course(version.course_id, course, f"Curriculum version {version.id}")
    _validate(session, version, body)

    setup = QuestionSetupRepository(session).add(
        QuestionSetupRow(
            curriculum_version_id=body.curriculum_version_id,
            approved_styles={
                str(entry.subtopic_id): list(dict.fromkeys(entry.style_ids))
                for entry in body.approved_styles
                if entry.style_ids
            },
            cell_targets=[cell.model_dump(mode="json") for cell in body.cell_targets],
        )
    )
    first = rounds.start_round(session, setup.id, size=body.round_size)
    session.commit()
    # Read off the module per request, so tests can replace the pipeline.
    background.add_task(rounds.run_round, first.id)
    return SaveSetupResponse(setup_id=setup.id, round_id=first.id)
