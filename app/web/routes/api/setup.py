"""Question setup: the style library, the AI-suggested setup, and saving it.

docs/QUESTION_SETUP_PLAN.md (agent A). Saving a setup starts round 1 in the background
(``app.generation.rounds.start_round`` then ``run_round``) and returns at once -- the ``/api/*``
proxy would time out on a synchronous round.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.courses.visibility import set_hidden, visibility_counts
from app.domain.enums import CurriculumStatus
from app.errors import DomainRuleError, NotFoundError
from app.generation import rounds
from app.jobs.queue import JobQueueDep
from app.llm import StructuredLLMClient
from app.persistence.models import CurriculumVersionRow, QuestionSetupRow
from app.persistence.repositories import (
    CurriculumRepository,
    GenerationRoundRepository,
    QuestionSetupRepository,
)
from app.styles import add_course_style, course_styles, get_library, styles_for, suggest_setup
from app.styles.loader import dump_style
from app.styles.schema import QuestionStyle
from app.subjects import profile_for_version
from app.web.routes.api.deps import (
    SPENDS_LLM_CREDIT,
    CourseProfile,
    CourseScope,
    DbSession,
    ensure_in_course,
    subtopics_in_course,
    version_in_course,
)
from app.web.routes.api.schemas import (
    CellVisibilityCount,
    CreateCourseStyleRequest,
    CurrentSetupResponse,
    QuestionSetupOut,
    QuestionVisibilityResponse,
    SaveSetupRequest,
    SaveSetupResponse,
    SetQuestionVisibilityRequest,
    SetQuestionVisibilityResponse,
    SetupSuggestionResponse,
    StyleListResponse,
    StyleVisibilityCount,
    SuggestSetupRequest,
    TypeVisibilityCount,
)

router = APIRouter(tags=["question-setup"])


def get_setup_client() -> StructuredLLMClient | None:
    """The structured client the suggester runs on. ``None`` lets it build its own from
    settings; tests override this with a fake."""
    return None


SetupClientDep = Annotated[StructuredLLMClient | None, Depends(get_setup_client)]


@router.get("/styles", response_model=StyleListResponse)
def list_styles(
    session: DbSession, profile: CourseProfile, subject: str | None = None
) -> StyleListResponse:
    """The styles of the course's subject and the course's own; another ``subject``'s library."""
    if subject is not None and subject != profile.storage_key:
        return StyleListResponse(subject=subject, styles=get_library(subject))
    styles = styles_for(session, profile)
    own = (
        {style.id for style in course_styles(session, profile.course_id)}
        if (profile.course_id is not None)
        else set()
    )
    return StyleListResponse(
        subject=profile.storage_key,
        styles=styles,
        course_style_ids=[style.id for style in styles if style.id in own],
    )


@router.post("/styles", response_model=QuestionStyle, status_code=status.HTTP_201_CREATED)
def create_course_style(
    session: DbSession, profile: CourseProfile, body: CreateCourseStyleRequest
) -> QuestionStyle:
    """Add a style to this course only. It must pass the library's CI checks."""
    return add_course_style(session, profile, body.yaml)


@router.get(
    "/styles/{style_id}/export",
    response_class=Response,
    responses={200: {"content": {"application/yaml": {}}}},
)
def export_style(session: DbSession, profile: CourseProfile, style_id: str) -> Response:
    """One style as a library file, ready for ``styles/<subject>/<id>.yaml`` in a PR."""
    style = next((s for s in styles_for(session, profile) if s.id == style_id), None)
    if style is None:
        raise NotFoundError(f"Style {style_id} not found.")
    return Response(
        dump_style(style),
        media_type="application/yaml",
        headers={"Content-Disposition": f'attachment; filename="{style.id}.yaml"'},
    )


@router.post(
    "/setup/suggest",
    response_model=SetupSuggestionResponse,
    dependencies=SPENDS_LLM_CREDIT,
)
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
    library = {style.id for style in styles_for(session, profile_for_version(session, version.id))}

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


@router.post(
    "/setup",
    response_model=SaveSetupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=SPENDS_LLM_CREDIT,
)
def save_setup(
    session: DbSession, course: CourseScope, body: SaveSetupRequest, queue: JobQueueDep
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
    queue.submit(rounds.run_round, first.id)
    return SaveSetupResponse(setup_id=setup.id, round_id=first.id)


def _require_course(course: int | None) -> int:
    if course is None:
        raise DomainRuleError("This request must name a course.")
    return course


@router.get("/question-visibility", response_model=QuestionVisibilityResponse)
def question_visibility(
    session: DbSession, course: CourseScope, curriculum_version_id: int | None = None
) -> QuestionVisibilityResponse:
    """Approved and hidden questions per style and type, and per subtopic of one taxonomy, so
    turning a style or type off can say how many questions it would hide (ADR-070)."""
    course_id = _require_course(course)
    if curriculum_version_id is not None:
        version_in_course(session, curriculum_version_id, course_id)
    counts = visibility_counts(session, course_id, curriculum_version_id=curriculum_version_id)
    return QuestionVisibilityResponse(
        by_style=[
            StyleVisibilityCount(style_id=key, approved=tally.approved, hidden=tally.hidden)
            for key, tally in sorted(counts.by_style.items())
        ],
        by_type=[
            TypeVisibilityCount(question_type=key, approved=tally.approved, hidden=tally.hidden)
            for key, tally in sorted(counts.by_type.items())
        ],
        by_cell=[
            CellVisibilityCount(
                subtopic_id=subtopic_id,
                style_id=style_id,
                difficulty=difficulty,
                approved=tally.approved,
                hidden=tally.hidden,
            )
            for (subtopic_id, style_id, difficulty), tally in counts.by_cell.items()
        ],
    )


@router.post("/question-visibility", response_model=SetQuestionVisibilityResponse)
def set_question_visibility(
    session: DbSession, course: CourseScope, body: SetQuestionVisibilityRequest
) -> SetQuestionVisibilityResponse:
    """Hide the course's approved questions in some styles or types from students, or show
    hidden ones again; course-wide or in one subtopic. Never a reject (ADR-070)."""
    course_id = _require_course(course)
    if body.subtopic_id is not None:
        subtopics_in_course(session, [body.subtopic_id], course_id)
    changed = set_hidden(
        session,
        course_id,
        hidden=body.hidden,
        style_ids=body.style_ids,
        question_types=body.question_types,
        subtopic_id=body.subtopic_id,
    )
    session.commit()
    return SetQuestionVisibilityResponse(changed=changed)
