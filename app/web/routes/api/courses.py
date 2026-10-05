"""Course endpoints: the list a professor picks from after login, and creating one.

A course is the workspace books and taxonomies are created in; every other
professor screen works inside one, naming it with the ``X-Course-Id`` header
(see :mod:`app.web.routes.api.deps`). There is no delete yet: a course owns
books and taxonomies, and what removing one should do to them is undecided.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.assessment import catalog
from app.courses.overview import SETUP_STEPS, build_overview
from app.errors import DomainRuleError
from app.persistence.models import CourseRow
from app.persistence.repositories import CourseRepository
from app.web.routes.api.deps import CurrentUser, DbSession
from app.web.routes.api.schemas import (
    ActivityEventOut,
    AssessmentCatalogResponse,
    CapabilityOut,
    CourseCreate,
    CourseListResponse,
    CourseOut,
    CourseProgressOut,
    CoursesOverviewResponse,
    CourseUpdate,
    MostMissedOut,
    QuestionTypeGroupOut,
    QuestionTypeOut,
    SetupStepOut,
    SubjectPresetOut,
)

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=CourseListResponse)
def list_courses(session: DbSession, user: CurrentUser) -> CourseListResponse:
    """The professor's own courses, newest first, with what has been built in each."""
    repo = CourseRepository(session)
    counts = repo.content_counts()
    return CourseListResponse(
        courses=[
            CourseOut.from_row(row, counts.get(row.id, (0, 0, 0)))
            for row in repo.list_all(owner_id=user.id)
        ]
    )


# Declared before "/{course_id}" so the literal path is not parsed as an id.
@router.get("/overview", response_model=CoursesOverviewResponse)
def courses_overview(session: DbSession, user: CurrentUser) -> CoursesOverviewResponse:
    """The course list's dashboard: each of the professor's courses, and recent activity."""
    overview = build_overview(session, owner_id=user.id)
    return CoursesOverviewResponse(
        courses=[
            CourseProgressOut(
                course=CourseOut.from_row(
                    p.course, (p.book_count, p.curriculum_version_count, p.question_count)
                ),
                owner_email=p.owner_email,
                owned_by_you=p.course.owner_id == user.id,
                proposed_curriculum_count=p.proposed_curriculum_count,
                approved_question_count=p.approved_question_count,
                awaiting_review_count=p.awaiting_review_count,
                question_set_count=p.question_set_count,
                student_count=p.student_count,
                coverage=p.coverage,
                avg_mastery=p.avg_mastery,
                most_missed=MostMissedOut(**vars(p.most_missed)) if p.most_missed else None,
                setup=[SetupStepOut(key=key, done=p.setup[key]) for key in SETUP_STEPS],
            )
            for p in overview.courses
        ],
        activity=[ActivityEventOut(**vars(event)) for event in overview.activity],
    )


@router.get("/catalog", response_model=AssessmentCatalogResponse)
def assessment_catalog() -> AssessmentCatalogResponse:
    """Subjects, question types and capabilities, for choosing what a new course assesses."""
    return AssessmentCatalogResponse(
        capabilities=[
            CapabilityOut(**vars(item), built=item.built) for item in catalog.CAPABILITIES
        ],
        question_types=[
            QuestionTypeOut(
                id=spec.id,
                label=spec.label,
                widget=spec.widget,
                group=spec.group,
                graded_by=list(spec.graded_by),
                also_needs=list(spec.also_needs),
                offerable=catalog.is_offerable(spec.id),
                ai_graded=all(
                    not catalog.CAPABILITIES_BY_ID[cap].deterministic for cap in spec.graded_by
                ),
            )
            for spec in catalog.QUESTION_TYPES
        ],
        groups=[
            QuestionTypeGroupOut(id=key, title=title, hint=hint)
            for key, (title, hint) in catalog.GROUPS.items()
        ],
        subjects=[
            SubjectPresetOut(
                id=preset.id,
                label=preset.label,
                description=preset.description,
                default_types=catalog.default_types_for(preset.id),
                coming_soon_types=[
                    type_id for type_id in preset.default_types if not catalog.is_offerable(type_id)
                ],
                primary_groups=list(preset.primary_groups),
                examples={
                    spec.id: catalog.example_for(preset.id, spec.id)
                    for spec in catalog.QUESTION_TYPES
                },
            )
            for preset in catalog.SUBJECTS
        ],
    )


def _chosen_types(body: CourseCreate) -> tuple[str, list[str]]:
    """The subject and question types to store, refusing anything that cannot be generated."""
    subject = body.subject or catalog.LEGACY_SUBJECT
    if subject not in catalog.SUBJECTS_BY_ID:
        raise DomainRuleError(f"Unknown subject {subject!r}.")
    if body.question_types is None:
        return subject, catalog.default_types_for(subject)
    chosen = list(dict.fromkeys(body.question_types))
    refused = [type_id for type_id in chosen if not catalog.is_offerable(type_id)]
    if refused:
        raise DomainRuleError(
            "Some question types cannot be used yet.",
            detail=f"Not available: {', '.join(refused)}.",
        )
    if not chosen:
        raise DomainRuleError("A course needs at least one question type.")
    return subject, chosen


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(session: DbSession, user: CurrentUser, body: CourseCreate) -> CourseOut:
    """Create an empty course owned by the professor creating it.

    The professor picks a subject and question types; the capabilities are worked out from the
    types and stored with them (ADR-054).
    """
    subject, types = _chosen_types(body)
    course = CourseRepository(session).add(
        CourseRow(
            name=body.name,
            description=body.description or None,
            owner_id=user.id,
            subject=subject,
            question_types=types,
            capabilities=catalog.capabilities_for(types),
        )
    )
    session.commit()
    return CourseOut.from_row(course)


@router.get("/{course_id}", response_model=CourseOut)
def get_course(session: DbSession, user: CurrentUser, course_id: int) -> CourseOut:
    repo = CourseRepository(session)
    course = repo.get_owned(course_id, user.id)
    return CourseOut.from_row(course, repo.content_counts().get(course_id, (0, 0, 0)))


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(
    session: DbSession, user: CurrentUser, course_id: int, body: CourseUpdate
) -> CourseOut:
    """Rename a course or change its description."""
    repo = CourseRepository(session)
    course = repo.get_owned(course_id, user.id)
    if body.name is not None and body.name.strip():
        course.name = body.name.strip()
    if body.description is not None:
        course.description = body.description.strip() or None
    session.commit()
    return CourseOut.from_row(course, repo.content_counts().get(course_id, (0, 0, 0)))
