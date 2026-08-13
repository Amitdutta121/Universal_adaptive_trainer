"""Question endpoints: generate section-grounded questions and read them back.

Generation always names an approved curriculum version; there is no path that
lets a caller invent taxonomy ids (ADR-001). Which generator ran is explicit and
recorded on the question, so ``base`` and ``personalized-context`` stay
distinguishable rather than being silently swapped (ADR-005).
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.errors import InvalidQuestionSpecError, NotFoundError
from app.evaluation import (
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
    humanize_judge_error_detail,
)
from app.generation import GenerationService
from app.persistence.models import QuestionRow
from app.persistence.repositories import CurriculumRepository, QuestionRepository
from app.personalization.embeddings import get_embedder
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import (
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    PersonalizationEvidence,
    QuestionDetail,
    QuestionListResponse,
    QuestionSummary,
    QuestionTaxonomy,
    ReviewOut,
    ReviewQueueMode,
    ReviewQueueResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("", response_model=QuestionListResponse)
def list_questions(session: DbSession, limit: int = 50) -> QuestionListResponse:
    """The question bank, newest first, with counts by lifecycle status."""
    repo = QuestionRepository(session)
    return QuestionListResponse(
        questions=[QuestionSummary.from_row(row) for row in repo.list_recent(limit=limit)],
        status_counts=repo.count_by_status(),
        total=repo.count(),
    )


@router.post(
    "/generate", response_model=GenerateQuestionsResponse, status_code=status.HTTP_201_CREATED
)
def generate_questions(
    session: DbSession, payload: GenerateQuestionsRequest
) -> GenerateQuestionsResponse:
    """Generate and persist one question per selected source section.

    Every spec is validated before the first model call, so an invalid id later
    in the list cannot leave a partially generated batch behind.
    """
    if payload.all_sections_of_book and payload.book_id is None:
        raise InvalidQuestionSpecError(
            "Generating from a whole book needs a book id.",
            detail="Set book_id, or list section_ids instead.",
        )
    if not payload.all_sections_of_book and not payload.section_ids:
        raise InvalidQuestionSpecError(
            "No source sections were selected.",
            detail="Provide section_ids, or set all_sections_of_book with a book_id.",
        )
    # Resolved before the service is built so that a missing curriculum reports
    # the fixable problem rather than an LLM-configuration error raised first.
    curriculum_version_id = payload.curriculum_version_id or approved_curriculum_id(session)

    service_kwargs: dict[str, Any] = {}
    if payload.generator == "personalized":
        service_kwargs["embedder"] = get_embedder()

    try:
        generated = GenerationService(session, **service_kwargs).generate_for_sections(
            curriculum_version_id=curriculum_version_id,
            question_type=payload.question_type,
            difficulty=payload.difficulty,
            source_section_ids=None if payload.all_sections_of_book else payload.section_ids,
            book_id=payload.book_id if payload.all_sections_of_book else None,
            seed=payload.seed,
            generator=payload.generator,
        )
    except Exception:
        session.rollback()
        raise

    return GenerateQuestionsResponse(
        created=len(generated),
        question_ids=[row.id for row in generated],
        questions=[QuestionSummary.from_row(row) for row in generated],
    )


def approved_curriculum_id(session: Session) -> int:
    """Return the approved curriculum id or raise an actionable generation error."""
    approved = CurriculumRepository(session).get_approved()
    if approved is None:
        raise InvalidQuestionSpecError(
            "No approved curriculum is available.",
            detail="Upload a valid taxonomy before generating questions.",
        )
    return approved.id


# Declared before "/{question_id}": FastAPI matches in registration order, so a
# literal path added after it would be parsed as a question id and 422.
@router.get("/review-queue", response_model=ReviewQueueResponse)
def review_queue(
    session: DbSession, after: int | None = None, mode: ReviewQueueMode = "all"
) -> ReviewQueueResponse:
    """The next question awaiting a professor verdict, plus progress counts.

    The queue holds no state. ``after`` is a plain cursor over question ids,
    which is what lets a professor skip a question -- and lets a submitted
    review advance to the next one -- without a stored position per professor.
    """
    repo = QuestionRepository(session)
    scoreable = [row for row in repo.list_unreviewed(require_evaluation=True) if _is_scoreable(row)]

    candidates = repo.list_unreviewed(after_id=after, require_evaluation=mode == "scoreable")
    if mode == "scoreable":
        candidates = [row for row in candidates if _is_scoreable(row)]

    total = repo.count()
    reviewed = repo.count_reviewed()
    return ReviewQueueResponse(
        mode=mode,
        total=total,
        reviewed=reviewed,
        remaining=total - reviewed,
        scoreable_remaining=len(scoreable),
        question=get_question(session, candidates[0].id) if candidates else None,
    )


def _is_scoreable(question: QuestionRow) -> bool:
    """Whether this question's stored evaluation can pair with a review.

    Calibration counts a question only when the judge actually reached a verdict,
    so an evaluation that errored, was skipped, or no longer validates is not a
    question worth reviewing *for alignment* -- it can never become a pair.
    """
    if question.pedagogical_eval is None:
        return False
    try:
        evaluation = PedagogicalEvaluation.model_validate(question.pedagogical_eval)
    except ValidationError:
        return False
    return evaluation.status is PedagogicalEvalStatus.COMPLETED


@router.get("/{question_id}", response_model=QuestionDetail)
def get_question(session: DbSession, question_id: int) -> QuestionDetail:
    """One question with its validation report, judge evaluation and provenance."""
    question = QuestionRepository(session).get(question_id)
    report = question.validation_report

    evaluation: PedagogicalEvaluation | None = None
    if question.pedagogical_eval is not None:
        with suppress(ValidationError):
            evaluation = PedagogicalEvaluation.model_validate(question.pedagogical_eval)

    content = question.content or {}
    sources = content.get("sources", [])

    return QuestionDetail(
        question=QuestionSummary.from_row(question),
        reference_solution=question.reference_solution,
        tests=question.tests,
        spec=question.spec,
        content=content,
        sources=sources if isinstance(sources, list) else [],
        taxonomy=resolve_taxonomy(session, question),
        validation_passed=report.passed if report is not None else None,
        validation_checks=report.checks if report is not None else [],
        pedagogical_eval=evaluation,
        pedagogical_error_message=(
            humanize_judge_error_detail(evaluation.error_detail)
            if evaluation is not None and evaluation.status is PedagogicalEvalStatus.ERROR
            else None
        ),
        personalization=personalization_evidence(question),
        original_prompt=question.original_prompt,
        original_reference_solution=question.original_reference_solution,
        original_tests=question.original_tests,
        reviews=[ReviewOut.from_row(review) for review in question.reviews],
    )


def resolve_taxonomy(session: Session, question: QuestionRow) -> QuestionTaxonomy:
    """Turn the ids on a question into display names, falling back to the id.

    A question keeps working after its curriculum version is superseded, so a
    name that can no longer be resolved degrades to an em dash rather than 404.
    """
    subtopic_ids = list(question.subtopic_ids)
    taxonomy = QuestionTaxonomy(
        curriculum=str(question.curriculum_version_id or "—"),
        topic=str(question.topic_id or "—"),
        subtopics=[str(subtopic_id) for subtopic_id in subtopic_ids] or ["—"],
    )
    if question.curriculum_version_id is None:
        return taxonomy
    try:
        version = CurriculumRepository(session).get_with_tree(question.curriculum_version_id)
    except NotFoundError:
        return taxonomy

    taxonomy.curriculum = version.label
    topic = next((item for item in version.topics if item.id == question.topic_id), None)
    if topic is None:
        return taxonomy
    taxonomy.topic = topic.name
    names = {item.id: item.name for item in topic.subtopics}
    if subtopic_ids:
        taxonomy.subtopics = [
            names.get(subtopic_id, str(subtopic_id)) for subtopic_id in subtopic_ids
        ]
    return taxonomy


def personalization_evidence(question: QuestionRow) -> PersonalizationEvidence | None:
    """The preferences and reviews recorded against a personalized question."""
    payload = question.personalization_context
    if question.generator_name != "personalized-context" or payload is None:
        return None
    preference_ids = payload.get("preference_ids", [])
    review_ids = payload.get("retrieved_review_ids", [])
    profile_version = payload.get("profile_version")
    return PersonalizationEvidence(
        preference_ids=preference_ids if isinstance(preference_ids, list) else [],
        review_ids=review_ids if isinstance(review_ids, list) else [],
        profile_version=str(profile_version) if profile_version is not None else None,
    )
