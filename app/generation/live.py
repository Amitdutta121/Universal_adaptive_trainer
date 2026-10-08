"""Live questions: generate one on demand when a student has nothing new to answer.

A student on a live classroom link asks for their next question. When the bank has nothing
to serve, or only a question this student has already answered, :func:`next_for_session`
plans one target for the cell the adaptive engine wanted and records a ``QUEUED``
:class:`LiveQuestionJobRow` instead of serving. :func:`run_live_job` then runs in the
background with the setup's aligned generator -- the same path as a setup round: an approved
style drawn by the professor's rejects, examples and "already in the bank" questions
(ADR-063 point 3), the answer check, the difficulty and topic judges and the custom rules, retried
with the failure reason and dropped if it still fails. The client polls ``/next``; once the
job is ``DONE`` that question is served to this student.

A live question passes every judge but has not necessarily been seen by the professor. It is
routed like any round question (auto-approved when the judges are trusted, otherwise left in
the review queue) and is servable to the student it was made for while it waits. Anyone
else gets it only once approved; a reject withdraws it.

Only managed classroom sets (:func:`app.adaptive.inventory.is_live_set`) with a question
setup generate: an ordinary frozen snapshot never gains questions.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.adaptive import AdaptiveTrainingEngine, ServedQuestion
from app.adaptive.inventory import is_live_set
from app.adaptive.selection import difficulty_fallback_order
from app.adaptive.service import DrawPlan
from app.domain.enums import Difficulty, RoundStatus
from app.errors import (
    AdaptiveTrainerError,
    InvalidQuestionSpecError,
    NoQuestionAvailableError,
)
from app.evaluation import new_run_id
from app.evaluation.custom import CustomRule
from app.generation.rounds import (
    _cell_styles,
    _hard_lesson_supported,
    _section_for,
    accepted_examples,
    default_embedder,
    style_rejects,
    style_weights,
)
from app.generation.spec import build_question_spec, require_approved_version
from app.llm import StructuredLLMClient
from app.persistence.models import LiveQuestionJobRow, QuestionRow, TrainingSessionRow
from app.persistence.repositories import (
    CustomJudgeRepository,
    LiveQuestionJobRepository,
    QuestionSetRepository,
    QuestionSetupRepository,
)
from app.retrieval import SectionEmbeddingStore, SectionRetriever
from app.retrieval.embedder import Embedder
from app.styles import get_library
from app.subjects import profile_for_version

logger = logging.getLogger(__name__)

#: A job still queued or running after this long is taken to have died with its worker.
LIVE_JOB_TIMEOUT = timedelta(minutes=10)
#: After a failed job, ``/next`` falls back to the bank for this long rather than paying for
#: another attempt on every poll. The student can still ask for one explicitly.
LIVE_RETRY_COOLDOWN = timedelta(minutes=5)


@dataclass(frozen=True)
class LiveTarget:
    setup_id: int
    subtopic_id: int
    requested: Difficulty
    difficulty: Difficulty
    style_id: str
    mastery: float


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _llm_ready() -> bool:
    from app.config import get_settings

    return get_settings().llm_configured


# ------------------------------------------------------------------ planning


def plan_target(
    session: Session,
    engine: AdaptiveTrainingEngine,
    run: TrainingSessionRow,
    plan: DrawPlan | None,
    *,
    rng: random.Random | None = None,
) -> LiveTarget | None:
    """The cell to generate for, with an approved style, or ``None`` when live is off.

    With a draw that only found a repeat, the drawn subtopic at the requested difficulty;
    with no draw at all, the engine's choice over the subtopics that have approved styles.
    The difficulty relaxes the way a draw does when no approved style can be written at it.
    """
    if run.set_version_id is None:
        return None
    bank = QuestionSetRepository(session).get(run.set_version_id)
    if not is_live_set(bank) or bank.curriculum_version_id is None:
        return None
    setup = QuestionSetupRepository(session).current(bank.curriculum_version_id)
    if setup is None:
        return None
    library = {
        style.id: style
        for style in get_library(
            profile_for_version(session, bank.curriculum_version_id).storage_key
        )
    }

    if plan is not None:
        subtopic_id, requested, mastery = plan.subtopic_id, plan.requested, plan.mastery
    else:
        candidates = {
            int(subtopic_id)
            for subtopic_id, styles in (setup.approved_styles or {}).items()
            if any(style_id in library for style_id in styles)
        }
        chosen = engine.live_target(run, candidates)
        if chosen is None:
            return None
        subtopic_id, requested, mastery = chosen

    rejects = style_rejects(session, bank.curriculum_version_id)
    for difficulty in difficulty_fallback_order(requested):
        cell = (subtopic_id, difficulty)
        styles = _cell_styles(setup, library, cell)
        weights = style_weights(styles, {s: rejects.get((cell, s), 0) for s in styles})
        pool = [s for s in styles if weights.get(s, 0) > 0]
        if pool:
            style_id = (rng or random.Random()).choices(pool, weights=[weights[s] for s in pool])[0]
            return LiveTarget(setup.id, subtopic_id, requested, difficulty, style_id, mastery)
    return None


def _lock_run(session: Session, training_session_id: int) -> None:
    """Serialize job creation for one session (a second tab, an overlapping poll)."""
    if session.get_bind().dialect.name == "sqlite":
        session.execute(
            update(TrainingSessionRow)
            .where(TrainingSessionRow.id == training_session_id)
            .values(id=TrainingSessionRow.id)
        )
    else:
        session.execute(
            select(TrainingSessionRow.id)
            .where(TrainingSessionRow.id == training_session_id)
            .with_for_update()
        )


def _expire_stale(session: Session, job: LiveQuestionJobRow) -> bool:
    """Fail a job whose worker evidently died; ``True`` when it did."""
    started = job.started_at or job.created_at
    if datetime.now(UTC) - _aware(started) < LIVE_JOB_TIMEOUT:
        return False
    job.status = RoundStatus.FAILED
    job.error = "Generating the question took too long."
    job.finished_at = datetime.now(UTC)
    session.flush()
    return True


def _in_cooldown(job: LiveQuestionJobRow | None) -> bool:
    if job is None or RoundStatus(job.status) is not RoundStatus.FAILED:
        return False
    finished = job.finished_at or job.created_at
    return datetime.now(UTC) - _aware(finished) < LIVE_RETRY_COOLDOWN


def next_for_session(
    session: Session, training_session_id: int, *, force: bool = False
) -> ServedQuestion | LiveQuestionJobRow:
    """Serve the next question, or the live job generating one. Flushes, does not commit.

    In order: the question already outstanding; a finished live question not yet served; a
    live job still running; a fresh bank draw unless it is empty or a repeat; else a new live
    job for the cell the draw wanted. When live generation is unavailable (not a classroom
    set, no setup, no approved style for the cell, no LLM, or a failure moments ago) the bank
    behaves as before: the repeat is served, or nothing is.

    ``force`` asks for a live question even right after a failure: the student pressed retry.

    Raises:
        NotFoundError, DomainRuleError, CurriculumCompletedError: as the engine does.
        NoQuestionAvailableError: nothing to serve and nothing to generate.
    """
    engine = AdaptiveTrainingEngine(session)
    jobs = LiveQuestionJobRepository(session)
    run = engine.open_run(training_session_id)
    resumed = engine.resume(run)
    if resumed is not None:
        return resumed

    ready = jobs.ready(run.id)
    if ready is not None:
        served = _serve_ready(session, engine, run, ready)
        if served is not None:
            return served

    active = jobs.active(run.id)
    if active is not None and not _expire_stale(session, active):
        return active

    try:
        plan: DrawPlan | None = engine.plan_draw(run)
        empty: NoQuestionAvailableError | None = None
    except NoQuestionAvailableError as exc:
        plan, empty = None, exc
    if plan is not None and not plan.repeat:
        return engine.serve_plan(run, plan)

    latest = jobs.latest(run.id)
    if (force or not _in_cooldown(latest)) and _llm_ready():
        target = plan_target(session, engine, run, plan)
        if target is not None:
            _lock_run(session, run.id)
            existing = jobs.active(run.id)
            if existing is not None:
                return existing
            return _create_job(session, run, target)

    if plan is not None:
        return engine.serve_plan(run, plan)
    assert empty is not None
    if latest is not None and latest.error and _in_cooldown(latest):
        raise NoQuestionAvailableError(
            "We couldn't make a new question for you just now.",
            detail=latest.error,
        )
    raise empty


def _serve_ready(
    session: Session,
    engine: AdaptiveTrainingEngine,
    run: TrainingSessionRow,
    job: LiveQuestionJobRow,
) -> ServedQuestion | None:
    question = session.get(QuestionRow, job.question_id)
    if question is None:
        job.status = RoundStatus.FAILED
        job.error = "The generated question was deleted before it was served."
        session.flush()
        return None
    try:
        served = engine.serve_live(
            run,
            question,
            subtopic_id=job.subtopic_id,
            requested=Difficulty(job.requested_difficulty),
            mastery=job.mastery,
        )
    except NoQuestionAvailableError:
        job.status = RoundStatus.FAILED
        job.error = "The professor withdrew the generated question before it was served."
        session.flush()
        return None
    job.attempt_id = served.attempt.id
    session.flush()
    return served


def _create_job(
    session: Session, run: TrainingSessionRow, target: LiveTarget
) -> LiveQuestionJobRow:
    job = LiveQuestionJobRepository(session).add(
        LiveQuestionJobRow(
            training_session_id=run.id,
            setup_id=target.setup_id,
            subtopic_id=target.subtopic_id,
            requested_difficulty=target.requested,
            difficulty=target.difficulty,
            style_id=target.style_id,
            mastery=target.mastery,
            status=RoundStatus.QUEUED,
        )
    )
    logger.info(
        "Session %s: live job %s for subtopic %s at %s (%s).",
        run.id,
        job.id,
        target.subtopic_id,
        target.difficulty.value,
        target.style_id,
    )
    return job


# ------------------------------------------------------------------ running


def _generate(
    session: Session,
    job: LiveQuestionJobRow,
    *,
    client: StructuredLLMClient | None,
    embedder: Embedder | None,
) -> QuestionRow | str:
    """One question for the job, or the reason there is none in the student's terms."""
    from app.generation.service import GenerationService

    setup = QuestionSetupRepository(session).get(job.setup_id) if job.setup_id else None
    if setup is None or job.subtopic_id is None:
        return "This classroom is no longer set up for new questions."
    version = require_approved_version(session, setup.curriculum_version_id)
    library = {
        style.id: style
        for style in get_library(profile_for_version(session, version.id).storage_key)
    }
    style = library.get(str(job.style_id))
    if style is None:
        return "The question style chosen for you is no longer available."
    retriever = (
        SectionRetriever(session, SectionEmbeddingStore(session, embedder))
        if embedder is not None
        else None
    )
    section_id = _section_for(retriever, version, job.subtopic_id)
    if section_id is None:
        return "No part of the book teaches this subtopic yet."

    difficulty = Difficulty(job.difficulty)
    if difficulty is Difficulty.HARD:
        supported, reason = _hard_lesson_supported(
            session,
            client,
            version_id=version.id,
            question_type=style.question_type.value,
            section_id=section_id,
        )
        if supported is False and Difficulty.MEDIUM in style.difficulty_range:
            logger.info("live job %s: hard unsupported (%s); generating medium", job.id, reason)
            difficulty = Difficulty.MEDIUM
            job.difficulty = difficulty
        elif supported is False:
            return "The book section for this subtopic cannot support a harder question."

    rules = [
        CustomRule.from_row(rule)
        for rule in CustomJudgeRepository(session).list_for_version(version.id, enabled_only=True)
    ]
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=style.question_type,
        difficulty=difficulty,
        source_section_ids=[section_id],
        target_subtopic_id=job.subtopic_id,
        style_id=style.id,
    )
    question = GenerationService(session, client=client).generate_round_question(
        spec,
        version=version,
        round_id=None,
        rules=rules,
        examples=accepted_examples(
            session,
            version.id,
            (job.subtopic_id, difficulty),
            style.question_type,
            section_id=section_id,
            embedder=embedder,
        ),
        run_id=new_run_id(),
    )
    if question is None:
        return "None of the drafts passed the professor's checks."
    question.live_generated = True
    session.flush()
    return question


def run_live_job(
    job_id: int,
    *,
    client: StructuredLLMClient | None = None,
    embedder: Embedder | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Background body: generate the job's question and record the outcome.

    Opens its own session. Claims the job ``QUEUED`` -> ``RUNNING`` so a repeated task is
    harmless, then ends ``DONE`` with ``question_id`` or ``FAILED`` with ``error``. Never
    raises out of the task.
    """
    if session_factory is None:
        from app.persistence.database import get_session_factory

        session_factory = get_session_factory()
    session = session_factory()
    try:
        claimed = session.execute(
            update(LiveQuestionJobRow)
            .where(
                LiveQuestionJobRow.id == job_id,
                LiveQuestionJobRow.status == RoundStatus.QUEUED,
            )
            .values(status=RoundStatus.RUNNING, started_at=datetime.now(UTC))
        )
        if claimed.rowcount != 1:
            session.rollback()
            return
        session.commit()
        job = LiveQuestionJobRepository(session).get(job_id)
        outcome = _generate(
            session,
            job,
            client=client,
            embedder=embedder if embedder is not None else default_embedder(),
        )
        if isinstance(outcome, str):
            job.status = RoundStatus.FAILED
            job.error = outcome
        else:
            job.status = RoundStatus.DONE
            job.question_id = outcome.id
        job.finished_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        logger.exception("live job %s failed", job_id)
        session.rollback()
        message = (
            exc.message
            if isinstance(exc, AdaptiveTrainerError)
            and not isinstance(exc, InvalidQuestionSpecError)
            else "Something went wrong while generating your question."
        )
        try:
            job = LiveQuestionJobRepository(session).get(job_id)
            job.status = RoundStatus.FAILED
            job.error = message
            job.finished_at = datetime.now(UTC)
            session.commit()
        except Exception:
            logger.exception("live job %s: could not record the failure", job_id)
            session.rollback()
    finally:
        session.close()


__all__ = ["LiveTarget", "next_for_session", "plan_target", "run_live_job"]
