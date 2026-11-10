"""Write path for professor approve / reject / edit reviews."""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.enums import (
    Difficulty,
    EvaluationTrigger,
    QuestionStatus,
    RejectionReason,
    ReviewDecision,
)
from app.domain.questions import Question, apply_professor_edit
from app.errors import ConfigurationError, DomainRuleError, NotFoundError
from app.evaluation import (
    PedagogicalEvaluation,
    PedagogicalJudge,
    new_run_id,
    record_evaluation,
)
from app.evaluation.severity import borderline_notes
from app.figures import figure_problems, parse_figure
from app.llm import StructuredLLMClient
from app.memory import (
    SOURCE_AUDIT,
    SOURCE_BORDERLINE,
    SOURCE_RETRY,
    SOURCE_REVIEW,
    MemoryEpisodeRepository,
    forget_review,
    record_review_episode,
    snapshot_question,
)
from app.persistence.models import (
    ProfessorReviewRow,
    QuestionRow,
    QuestionSubtopicRow,
    QuestionVariantRow,
    ReviewOutcomeRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository

_EDITABLE = ("prompt", "reference_solution", "tests")


def _norm(value: str | None) -> str:
    return "" if value is None else value


def submit_review(
    session: Session,
    *,
    question_id: int,
    decision: ReviewDecision,
    reasons: list[RejectionReason] | None = None,
    comment: str | None = None,
    prompt: str | None = None,
    reference_solution: str | None = None,
    tests: str | None = None,
    figure: dict | None = None,
    professor_id: int | None = None,
    corrected_difficulty: Difficulty | None = None,
    corrected_subtopic_ids: list[int] | None = None,
) -> ProfessorReviewRow:
    """Append a professor review and update the question's usable status.

    Edit updates current question fields but never touches ``original_*``.
    ``changed_fields`` are derived here by comparing submitted values to the
    persisted question, never trusted from the client.

    ``figure`` (edit only; ``None`` leaves it as it is) replaces the question's figure, of
    the same kind. It must be drawable (:func:`app.figures.figure_problems`), and a computed
    figure may change only its ``alt`` and ``caption``: its picture is the program's.

    ``corrected_difficulty`` / ``corrected_subtopic_ids`` are what the professor says the
    question really is (the review form requires explicit confirmation). They are
    stored as given, whatever the decision, because attribution reads them as direct
    evidence about the difficulty and subtopic judges. Rejection permits an optional
    comment without requiring structured reasons or classification corrections.

    The review is also written into memory as an episode (:mod:`app.memory`, ADR-063): the
    question as reviewed, the verdict, and the judges' verdicts. No model call.
    """
    question = QuestionRepository(session).get(question_id)
    reviewed = snapshot_question(question)
    reason_list = list(reasons or [])
    if corrected_subtopic_ids is not None:
        if not corrected_subtopic_ids:
            raise DomainRuleError("A subtopic correction must name at least one subtopic.")
        _check_subtopics_in_taxonomy(session, question, corrected_subtopic_ids)

    edited_prompt: str | None = None
    edited_reference_solution: str | None = None
    edited_tests: str | None = None
    edited_figure: dict | None = None
    changed_fields: list[str] = []

    if decision is ReviewDecision.APPROVE:
        reason_list = []
        question.status = QuestionStatus.APPROVED
    elif decision is ReviewDecision.REJECT:
        question.status = QuestionStatus.REJECTED
    elif decision is ReviewDecision.EDIT:
        if prompt is None or reference_solution is None or tests is None:
            raise DomainRuleError(
                "Edit requires prompt, reference_solution, and tests "
                "(use empty string when unused)."
            )
        if not prompt.strip():
            raise DomainRuleError("Edited prompt must not be empty.")

        edited_prompt = prompt
        edited_reference_solution = reference_solution
        edited_tests = tests
        current = {
            "prompt": _norm(question.prompt),
            "reference_solution": _norm(question.reference_solution),
            "tests": _norm(question.tests),
        }
        submitted = {
            "prompt": edited_prompt,
            "reference_solution": edited_reference_solution,
            "tests": edited_tests,
        }
        changed_fields = [name for name in _EDITABLE if current[name] != submitted[name]]
        edited_figure = _edited_figure(question, figure)
        if edited_figure is not None:
            changed_fields.append("figure")
        if not changed_fields:
            raise DomainRuleError("Edit requires at least one changed field.")

        before_edit = Question.model_validate(question)
        edited_question = apply_professor_edit(
            before_edit,
            prompt=edited_prompt,
            reference_solution=edited_reference_solution,
            tests=edited_tests,
        )
        # Persist the generated text before overwriting it. ``Question`` seeds
        # ``original_*`` on construction, but only on the domain copy; a row that
        # reached the database without them would otherwise lose the generated
        # version here, and "generated vs. accepted" (ADR-002) is exactly what a
        # judge repair and a generator refresh both read.
        if question.original_prompt is None:
            question.original_prompt = before_edit.original_prompt
        if question.original_reference_solution is None:
            question.original_reference_solution = before_edit.original_reference_solution
        if question.original_tests is None:
            question.original_tests = before_edit.original_tests
        question.prompt = edited_question.prompt
        question.reference_solution = edited_question.reference_solution
        question.tests = edited_question.tests
        if edited_figure is not None:
            _apply_figure(session, question, edited_figure)
        question.updated_at = edited_question.updated_at
        question.status = QuestionStatus.APPROVED
    else:
        raise DomainRuleError(f"Unsupported review decision: {decision}")

    # Keep original classification in the frozen generation spec for older judge
    # blobs whose passing verdict did not include its proposed value.
    spec = dict(question.spec or {})
    if corrected_difficulty is not None or corrected_subtopic_ids is not None:
        spec.setdefault("difficulty", question.difficulty.value)
        spec.setdefault("topic_id", question.topic_id)
        spec.setdefault("subtopic_ids", list(question.subtopic_ids))
        question.spec = spec
    if decision in (ReviewDecision.APPROVE, ReviewDecision.EDIT):
        if corrected_difficulty is not None:
            question.difficulty = corrected_difficulty
        if corrected_subtopic_ids is not None:
            ids = list(dict.fromkeys(corrected_subtopic_ids))
            # Keep existing association rows by difference to preserve retained
            # join rows and avoid unique-key collisions during flush.
            question.subtopic_links = [
                link for link in question.subtopic_links if link.subtopic_id in ids
            ]
            retained = {link.subtopic_id for link in question.subtopic_links}
            question.subtopic_links.extend(
                QuestionSubtopicRow(subtopic_id=sid) for sid in ids if sid not in retained
            )
            question.topic_id = session.get(SubtopicRow, ids[0]).topic_id

    review = ProfessorReviewRow(
        question_id=question.id,
        decision=decision,
        reasons=reason_list,
        comment=comment,
        edited_prompt=edited_prompt,
        edited_reference_solution=edited_reference_solution,
        edited_tests=edited_tests,
        edited_figure=edited_figure,
        changed_fields=changed_fields,
        professor_id=professor_id,
        corrected_difficulty=corrected_difficulty,
        corrected_subtopic_ids=(
            list(dict.fromkeys(corrected_subtopic_ids))
            if corrected_subtopic_ids is not None
            else None
        ),
        reviewed_generator_name=question.generator_name,
        reviewed_generator_version=question.generator_version,
    )
    review = ProfessorReviewRepository(session).add(review)
    record_review_episode(session, review, reviewed, source=_episode_source(question))
    return review


def rejudge_edited_figure(
    session: Session, review: ProfessorReviewRow, *, client: StructuredLLMClient | None = None
) -> bool:
    """Judge a question again after an edit that changed its figure. Flushes; never commits.

    Run after the review's outcome is routed, so the outcome keeps the verdict the professor
    reviewed. The new evaluation is appended to the question's history (trigger
    ``professor_edit``) and becomes current. ``False`` when nothing was judged: the edit kept
    the figure, or no model is configured.
    """
    if "figure" not in (review.changed_fields or []):
        return False
    try:
        judge = PedagogicalJudge(session, client=client)
    except ConfigurationError:
        return False
    question = QuestionRepository(session).get(review.question_id)
    evaluation = judge.evaluate(Question.model_validate(question))
    record_evaluation(
        session,
        question.id,
        evaluation.model_copy(update={"question_id": question.id}),
        run_id=new_run_id(),
        trigger=EvaluationTrigger.PROFESSOR_EDIT,
    )
    session.flush()
    return True


def _edited_figure(question: QuestionRow, figure: dict | None) -> dict | None:
    """The submitted figure, validated and normalized; ``None`` when it changes nothing."""
    if figure is None:
        return None
    current = (question.content or {}).get("figure")
    if not isinstance(current, dict):
        raise DomainRuleError("This question has no figure to edit.")
    problems = figure_problems(figure)
    if problems:
        raise DomainRuleError("The edited figure cannot be shown.", detail="; ".join(problems))
    edited = parse_figure(figure).model_dump(mode="json")
    if edited["kind"] != current.get("kind"):
        raise DomainRuleError(
            "An edited figure keeps its kind.",
            detail=f"The figure is a {current.get('kind')}, not a {edited['kind']}.",
        )
    if edited["kind"] == "computed" and edited["file"] != current.get("file"):
        raise DomainRuleError(
            "A computed figure is drawn by its program; edit only its alt text and caption.",
            detail="Regenerate the copy for a new picture.",
        )
    try:
        unchanged = edited == parse_figure(current).model_dump(mode="json")
    except ValidationError:
        unchanged = False
    return None if unchanged else edited


def _apply_figure(session: Session, question: QuestionRow, figure: dict) -> None:
    """Make ``figure`` the question's, keeping the generated one (ADR-002)."""
    content = dict(question.content or {})
    if question.original_figure is None:
        question.original_figure = content.get("figure")
    content["figure"] = figure
    question.content = content
    # Copy 0 of a computed question is its content (``app.generation.computed``).
    first = session.scalar(
        select(QuestionVariantRow).where(
            QuestionVariantRow.question_id == question.id, QuestionVariantRow.ordinal == 0
        )
    )
    if first is not None:
        first.content = {**(first.content or {}), "figure": figure}


def delete_review(session: Session, review_id: int) -> None:
    """Delete a review, its episode and its outcome. Flushes; the caller commits.

    The episode goes with the review (ORM cascade), so it is never retrieved again; the
    outcome row is deleted explicitly because SQLite enforces no ``ondelete``. The review
    stops supporting any guideline it taught (:func:`app.memory.forget_review`), and the retry
    episodes its approval let the question's failed attempts teach go too. The question
    keeps whatever status and fields the review gave it.
    """
    review = session.get(ProfessorReviewRow, review_id)
    if review is None:
        raise NotFoundError(f"Review {review_id} not found.")
    session.execute(delete(ReviewOutcomeRow).where(ReviewOutcomeRow.review_id == review_id))
    forget_review(session, review_id)
    MemoryEpisodeRepository(session).delete_of_source(SOURCE_RETRY, question_id=review.question_id)
    session.delete(review)
    session.flush()


def _episode_source(question: QuestionRow) -> str:
    """Audit and borderline keeps are their own episode sources (m9, m10)."""
    if question.audit:
        return SOURCE_AUDIT
    spec = question.spec if isinstance(question.spec, dict) else {}
    try:
        requested = Difficulty(spec.get("difficulty") or question.difficulty)
    except ValueError:
        requested = question.difficulty
    target = question.target_subtopic_id
    evaluation = None
    if isinstance(question.pedagogical_eval, dict):
        try:
            evaluation = PedagogicalEvaluation.model_validate(question.pedagogical_eval)
        except ValidationError:
            evaluation = None
    if target is not None and borderline_notes(
        evaluation, requested_difficulty=requested, target_subtopic_id=target
    ):
        return SOURCE_BORDERLINE
    return SOURCE_REVIEW


def _check_subtopics_in_taxonomy(
    session: Session, question: QuestionRow, subtopic_ids: list[int]
) -> None:
    """Refuse a subtopic correction naming a subtopic outside the question's taxonomy.

    A foreign id would be recorded as the professor's verdict and then counted against
    the subtopic judge, which could never have proposed it.
    """
    if question.curriculum_version_id is None:
        raise DomainRuleError("Subtopic corrections require a question taxonomy.")
    known = set(
        session.scalars(
            select(SubtopicRow.id)
            .join(TopicRow, SubtopicRow.topic_id == TopicRow.id)
            .where(TopicRow.curriculum_version_id == question.curriculum_version_id)
        )
    )
    unknown = sorted(set(subtopic_ids) - known)
    if unknown:
        raise DomainRuleError(
            "Corrected subtopics must belong to the question's taxonomy.",
            detail=f"unknown subtopic ids: {unknown}",
        )
