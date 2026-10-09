"""Generation rounds of a question setup: pick targets, generate in the background.

docs/QUESTION_SETUP_PLAN.md, agent B. The setup routes call :func:`start_round`; the rounds
route calls :func:`next_round`; both hand :func:`run_round` to a background task after the
request commits, and the client polls ``GET /api/rounds/{id}``.

Planning (synchronous, no model call):

* A **cell** is one subtopic x difficulty of the setup's ``cell_targets``. Its count is the
  approved + pending-review questions of the taxonomy in that cell; only cells below target
  get targets, spread one per cell per pass, neediest first.
* The **style** of each target is drawn by weight from the styles approved for its subtopic
  (and able to be written at that difficulty): each professor reject of a round question
  in that style and cell halves the weight, two rejects exclude it. When every style is
  excluded, the least-rejected ones are used rather than leaving the cell unreachable.

Running (background): first the **lesson run** (ADR-063) learns from the reviews since the
last round, so the whole round is generated with them; a failure there is recorded on the
round and does not stop it. Then, per target, retrieve the section that best teaches the subtopic
(embedding retrieval as in ``POST /coverage/generation-runs``, falling back to the
subtopic's evidence section). A hard target asks the generatability judge once, before
any draft: if the lesson cannot support a hard question, the target is skipped and the
reason is stored, separate from a drop. Otherwise
:meth:`GenerationService.generate_round_question` judges inside the retry loop and drops
what still fails after the last attempt -- except a duplicate of a stored question, which is
retried and, on the last attempt, kept with a similarity flag (ADR-063 point 6). Once the
targets are done, a deterministic **drift check** (:mod:`app.generation.drift`) compares the
round's questions with the previous round's and stores any warning on the round.
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionStatus, QuestionType, RoundStatus
from app.errors import (
    AdaptiveTrainerError,
    ConfigurationError,
    DomainRuleError,
    InvalidQuestionSpecError,
    LLMRequestError,
    MalformedModelOutputError,
)
from app.evaluation import new_run_id
from app.evaluation.custom import CustomRule
from app.evaluation.service import PedagogicalJudge
from app.feedback.lessons import apply_pending_lessons
from app.generation.drift import check_round_drift
from app.generation.prompts import (
    RejectedExample,
    RoundExamples,
    ShownExample,
)
from app.generation.spec import build_question_spec, require_approved_version
from app.ingestion.retrieval import SourceRetrieval
from app.jobs.cancel import CANCELLED, JobCancelled, raise_if_cancelled
from app.llm import StructuredLLMClient
from app.persistence.models import (
    CurriculumVersionRow,
    GenerationRoundRow,
    QuestionRow,
    QuestionSetupRow,
)
from app.persistence.repositories import (
    CustomJudgeRepository,
    GenerationRoundRepository,
    QuestionSetupRepository,
)
from app.retrieval import SectionEmbeddingStore, SectionRetriever
from app.retrieval.duplicates import DuplicateChecker
from app.retrieval.embedder import Embedder
from app.retrieval.examples import retrieve_for_target
from app.styles import QuestionStyle, get_library
from app.subjects import profile_for_version

logger = logging.getLogger(__name__)

#: Questions per round unless the caller asks otherwise.
DEFAULT_ROUND_SIZE = 10

#: Each professor reject of a style in a cell multiplies its weight by this.
STYLE_REJECT_FACTOR = 0.5
#: A style rejected this many times in a cell is no longer drawn there.
STYLE_EXCLUDE_REJECTS = 2
#: Accepted questions shown to the generator as examples (same type; ADR-063 point 3).
MAX_EXAMPLES_PER_CELL = 2

#: Same floor as ``app.web.routes.api.coverage.MIN_SECTION_SCORE`` (generation must not
#: import ``app.web``): below it a retrieved section is not trusted to teach the subtopic.
MIN_SECTION_SCORE = 0.25

#: Statuses that count toward a cell: approved, or still waiting for the professor.
#: ``VALIDATION_FAILED`` is not offered for review, and a reject is not coverage.
_COUNTED_STATUSES = (
    QuestionStatus.APPROVED,
    QuestionStatus.GENERATED,
    QuestionStatus.VALIDATION_PASSED,
)

Cell = tuple[int, Difficulty]


# ------------------------------------------------------------------ planning


def cell_counts(session: Session, curriculum_version_id: int) -> dict[Cell, int]:
    """Approved + pending-review questions per (subtopic, difficulty) of one taxonomy.

    A question counts in every subtopic it is tagged with, as on the coverage grid, and also
    in the subtopic it was generated for, so a pending round question fills its target cell
    even before the professor confirms its tags.
    """
    stmt = select(QuestionRow).where(
        QuestionRow.curriculum_version_id == curriculum_version_id,
        QuestionRow.status.in_(_COUNTED_STATUSES),
    )
    counts: dict[Cell, int] = defaultdict(int)
    for question in session.scalars(stmt):
        subtopics = set(question.subtopic_ids)
        if question.target_subtopic_id is not None:
            subtopics.add(question.target_subtopic_id)
        for subtopic_id in subtopics:
            counts[(subtopic_id, Difficulty(question.difficulty))] += 1
    return dict(counts)


def style_rejects(session: Session, curriculum_version_id: int) -> dict[tuple[Cell, str], int]:
    """How many round questions of each style the professor rejected, per target cell."""
    stmt = select(
        QuestionRow.target_subtopic_id, QuestionRow.difficulty, QuestionRow.style_id
    ).where(
        QuestionRow.curriculum_version_id == curriculum_version_id,
        QuestionRow.status == QuestionStatus.REJECTED,
        QuestionRow.style_id.is_not(None),
        QuestionRow.target_subtopic_id.is_not(None),
    )
    rejects: dict[tuple[Cell, str], int] = defaultdict(int)
    for subtopic_id, difficulty, style_id in session.execute(stmt):
        rejects[((subtopic_id, Difficulty(difficulty)), style_id)] += 1
    return dict(rejects)


def style_weights(style_ids: list[str], rejects: dict[str, int]) -> dict[str, float]:
    """Draw weight per style for one cell: halved per reject, excluded at two.

    When every style is excluded, the least-rejected ones get weight 1 so the cell can still
    be filled; the professor approved those styles, and a cell with no way to reach its
    target would stall every later round.
    """
    weights = {
        style_id: (
            STYLE_REJECT_FACTOR ** rejects.get(style_id, 0)
            if rejects.get(style_id, 0) < STYLE_EXCLUDE_REJECTS
            else 0.0
        )
        for style_id in style_ids
    }
    if style_ids and not any(weights.values()):
        fewest = min(rejects.get(style_id, 0) for style_id in style_ids)
        weights = {
            style_id: 1.0 if rejects.get(style_id, 0) == fewest else 0.0 for style_id in style_ids
        }
    return weights


def _cell_styles(
    setup: QuestionSetupRow, library: dict[str, QuestionStyle], cell: Cell
) -> list[str]:
    """Approved, known styles for the cell's subtopic, preferring those fit for its difficulty."""
    subtopic_id, difficulty = cell
    approved = [
        style_id
        for style_id in (setup.approved_styles or {}).get(str(subtopic_id), [])
        if style_id in library
    ]
    return [s for s in approved if difficulty in library[s].difficulty_range]


def plan_targets(
    session: Session,
    setup: QuestionSetupRow,
    *,
    size: int,
    rng: random.Random | None = None,
    cell_deficits: dict[Cell, int] | None = None,
) -> list[dict[str, object]]:
    """Up to ``size`` targets ``{"subtopic_id", "difficulty", "style_id"}`` for one round."""
    rng = rng or random.Random()
    version = require_approved_version(session, setup.curriculum_version_id)
    known_subtopics = {s.id for topic in version.topics for s in topic.subtopics}
    profile = profile_for_version(session, version.id)
    library = {style.id: style for style in get_library(profile.storage_key)}
    counts = cell_counts(session, version.id)
    rejects = style_rejects(session, version.id)

    order: list[Cell] = []
    deficit: dict[Cell, int] = {}
    styles: dict[Cell, list[str]] = {}
    for entry in setup.cell_targets or []:
        cell = (int(entry["subtopic_id"]), Difficulty(entry["difficulty"]))
        if cell[0] not in known_subtopics or cell in deficit:
            continue
        missing = (
            cell_deficits.get(cell, 0)
            if cell_deficits is not None
            else int(entry["target"]) - counts.get(cell, 0)
        )
        candidates = _cell_styles(setup, library, cell)
        if missing <= 0 or not candidates:
            continue
        order.append(cell)
        deficit[cell] = missing
        styles[cell] = candidates

    targets: list[dict[str, object]] = []
    # One target per cell per pass, neediest first, so a round spreads across cells rather
    # than filling the first ones in taxonomy order.
    while len(targets) < size and any(deficit.values()):
        for cell in sorted(
            (c for c in order if deficit[c] > 0), key=lambda c: (-deficit[c], order.index(c))
        ):
            if len(targets) >= size:
                break
            weights = style_weights(
                styles[cell], {s: rejects.get((cell, s), 0) for s in styles[cell]}
            )
            pool = [s for s in styles[cell] if weights[s] > 0]
            style_id = rng.choices(pool, weights=[weights[s] for s in pool])[0]
            targets.append(
                {"subtopic_id": cell[0], "difficulty": cell[1].value, "style_id": style_id}
            )
            deficit[cell] -= 1
    return targets


def active_round(session: Session, curriculum_version_id: int) -> GenerationRoundRow | None:
    """Any active round of this taxonomy, including older setup revisions."""
    return session.scalars(
        select(GenerationRoundRow)
        .join(QuestionSetupRow)
        .where(
            QuestionSetupRow.curriculum_version_id == curriculum_version_id,
            GenerationRoundRow.status.in_((RoundStatus.QUEUED, RoundStatus.RUNNING)),
        )
        .order_by(GenerationRoundRow.id)
        .limit(1)
    ).first()


def _lock_taxonomy(session: Session, curriculum_version_id: int) -> None:
    """Serialize all round planners, including classroom and professor callers."""
    if session.get_bind().dialect.name == "sqlite":
        # SELECT FOR UPDATE is ignored by SQLite; a value-preserving write takes
        # its writer lock before the active-round check and numbering query.
        session.execute(
            update(CurriculumVersionRow)
            .where(
                CurriculumVersionRow.id == curriculum_version_id,
            )
            .values(id=CurriculumVersionRow.id)
        )
    else:
        session.execute(
            select(CurriculumVersionRow.id)
            .where(
                CurriculumVersionRow.id == curriculum_version_id,
            )
            .with_for_update()
        )


def refill_round(
    session: Session,
    setup_id: int,
    cell_deficits: dict[Cell, int],
    *,
    size: int = DEFAULT_ROUND_SIZE,
    rng: random.Random | None = None,
) -> GenerationRoundRow | None:
    """Plan unseen-stock replenishment even when professor coverage is full.

    Caller serializes planning and commits before running the round. Does not
    generate, inspect correctness, or alter setup coverage targets.
    """
    setup = QuestionSetupRepository(session).get(setup_id)
    _lock_taxonomy(session, setup.curriculum_version_id)
    if active_round(session, setup.curriculum_version_id) is not None:
        return None
    targets = plan_targets(
        session,
        setup,
        size=max(0, min(size, DEFAULT_ROUND_SIZE)),
        rng=rng,
        cell_deficits=cell_deficits,
    )
    if not targets:
        return None
    rounds = GenerationRoundRepository(session)
    return rounds.add(
        GenerationRoundRow(
            setup_id=setup.id,
            number=rounds.next_number(setup.id),
            targets=targets,
            requested=len(targets),
            status=RoundStatus.QUEUED,
        )
    )


def _create_round(
    session: Session, setup: QuestionSetupRow, *, size: int, rng: random.Random | None
) -> GenerationRoundRow:
    rounds = GenerationRoundRepository(session)
    targets = plan_targets(session, setup, size=size, rng=rng)
    row = GenerationRoundRow(
        setup_id=setup.id,
        number=rounds.next_number(setup.id),
        targets=targets,
        requested=len(targets),
        status=RoundStatus.QUEUED if targets else RoundStatus.DONE,
    )
    if not targets:
        row.finished_at = datetime.now(UTC)
    return rounds.add(row)


def start_round(
    session: Session,
    setup_id: int,
    *,
    size: int = DEFAULT_ROUND_SIZE,
    rng: random.Random | None = None,
) -> GenerationRoundRow:
    """Create round 1 of a freshly saved setup, ``QUEUED``, with its targets chosen.

    Same selection as :func:`next_round`; separate so the setup route's intent is explicit and
    so it can refuse a setup that already has rounds. Flushes, does not commit, and does not
    generate: the caller commits and schedules ``run_round(row.id)``.

    Raises:
        NotFoundError: the setup does not exist.
        DomainRuleError: the setup already has a round.
    """
    setup = QuestionSetupRepository(session).get(setup_id)
    _lock_taxonomy(session, setup.curriculum_version_id)
    if GenerationRoundRepository(session).latest(setup_id) is not None:
        raise DomainRuleError(
            "This setup has already started generating.",
            detail=f"Setup {setup_id} already has rounds; ask for the next round instead.",
        )
    if active_round(session, setup.curriculum_version_id) is not None:
        raise DomainRuleError("A round of this taxonomy is still generating.")
    return _create_round(session, setup, size=size, rng=rng)


def next_round(
    session: Session,
    setup_id: int,
    *,
    size: int = DEFAULT_ROUND_SIZE,
    rng: random.Random | None = None,
) -> GenerationRoundRow:
    """Create the next round of a setup, ``QUEUED``, targeting cells still below target.

    Picks up to ``size`` targets ``{"subtopic_id", "difficulty", "style_id"}`` from cells whose
    approved + pending count is below the setup's ``cell_targets``; the style per cell is drawn
    by weight (each reject of that style in that cell halves it; two rejects exclude it).
    ``requested`` is the number of targets, which may be fewer than ``size``. When every cell
    is full the round is created ``DONE`` with ``requested == 0``; the route turns that into a
    message instead of committing it. Flushes, does not commit, does not generate.

    Raises:
        NotFoundError: the setup does not exist.
        DomainRuleError: a round of this setup is still ``QUEUED`` or ``RUNNING``.
    """
    setup = QuestionSetupRepository(session).get(setup_id)
    _lock_taxonomy(session, setup.curriculum_version_id)
    latest = active_round(session, setup.curriculum_version_id)
    if latest is not None:
        raise DomainRuleError(
            "A round of this setup is still generating.",
            detail=f"Round {latest.number} is {RoundStatus(latest.status).value}; wait for it.",
        )
    return _create_round(session, setup, size=size, rng=rng)


# ------------------------------------------------------------------ running


def default_embedder() -> Embedder | None:
    """The live embedder for section retrieval, or ``None`` when none is configured.

    Without one, a target falls back to its subtopic's evidence section.
    """
    from app.config import get_settings
    from app.retrieval import get_embedder

    try:
        return get_embedder(get_settings())
    except ConfigurationError:
        return None


def _section_for(
    retriever: SectionRetriever | None, version: CurriculumVersionRow, subtopic_id: int
) -> int | None:
    """The book section to ground a target in: best retrieval hit, else evidence."""
    if retriever is not None:
        try:
            hits = retriever.for_subtopic(subtopic_id, top_k=1)
        except AdaptiveTrainerError as exc:
            logger.warning("round: retrieval failed for subtopic %s: %s", subtopic_id, exc)
            hits = []
        if hits and hits[0].score >= MIN_SECTION_SCORE:
            return hits[0].section_id
    for topic in version.topics:
        for subtopic in topic.subtopics:
            if subtopic.id == subtopic_id and subtopic.evidence:
                return subtopic.evidence[0].section_id
    return None


def accepted_examples(
    session: Session,
    curriculum_version_id: int,
    cell: Cell,
    question_type: QuestionType,
    *,
    section_id: int | None = None,
    embedder: Embedder | None = None,
    limit: int = MAX_EXAMPLES_PER_CELL,
) -> RoundExamples:
    """Approved questions of ``question_type`` to match, the cell's questions not to repeat,
    at most one similar question the professor rejected, with why, and the retry lessons of
    the type and subtopic.

    Examples and the rejected question come from the memory episodes of the course's subject
    (:mod:`app.memory`), examples with the professor's comment. The order is
    :func:`app.retrieval.examples.retrieve_for_target`'s (ADR-063 point 3): the cell, then the
    same topic, then the rest, by similarity to the target's ``section_id`` when there is an
    embedder; examples from outside the cell are labelled "style only".
    """
    subtopic_id, difficulty = cell
    section_text = (
        SourceRetrieval(session).get_section(section_id).text if section_id is not None else ""
    )
    found = retrieve_for_target(
        session,
        embedder,
        curriculum_version_id=curriculum_version_id,
        subject=profile_for_version(session, curriculum_version_id).personal_key,
        question_type=question_type,
        subtopic_id=subtopic_id,
        difficulty=difficulty,
        section_text=section_text,
        limit=limit,
    )
    rejected = found.rejected
    return RoundExamples(
        accepted=[
            ShownExample(example.text, example.comment)
            for example in found.examples
            if example.same_cell
        ],
        style_only=[
            ShownExample(example.text, example.comment)
            for example in found.examples
            if not example.same_cell
        ],
        in_bank=[question.text for question in found.in_bank],
        rejected=RejectedExample(rejected.text, rejected.because) if rejected else None,
        avoid=found.avoid,
    )


def _skip_reason(notes: list[str]) -> str | None:
    if not notes:
        return None
    return "; ".join(notes)[:500]


def _hard_lesson_supported(
    session: Session,
    client: StructuredLLMClient | None,
    *,
    version_id: int,
    question_type: str,
    section_id: int,
) -> tuple[bool | None, str]:
    """One generatability call. False means skip this hard target and write no drafts."""
    retrieval = SourceRetrieval(session)
    section = retrieval.get_section(section_id)
    citation = retrieval.section_source(section_id).citation()
    judge = PedagogicalJudge(session, client=client)
    return judge.section_supports(
        curriculum_version_id=version_id,
        difficulty=Difficulty.HARD.value,
        question_type=question_type,
        section_text=section.text,
        citation=citation,
    )


def _generate_round(
    session: Session,
    row: GenerationRoundRow,
    *,
    client: StructuredLLMClient | None,
    embedder: Embedder | None,
) -> None:
    """Generate every target of a running round, committing after each one."""
    from app.generation.service import GenerationService

    rounds = GenerationRoundRepository(session)
    round_id = row.id
    setup = QuestionSetupRepository(session).get(row.setup_id)
    version = require_approved_version(session, setup.curriculum_version_id)
    version_id = version.id
    rules = [
        CustomRule.from_row(rule)
        for rule in CustomJudgeRepository(session).list_for_version(version_id, enabled_only=True)
    ]
    library = {
        style.id: style
        for style in get_library(profile_for_version(session, version_id).storage_key)
    }
    retriever = (
        SectionRetriever(session, SectionEmbeddingStore(session, embedder))
        if embedder is not None
        else None
    )
    service = GenerationService(session, client=client)
    # Without an embedder only exact duplicates are caught (ADR-063 point 6).
    duplicates = DuplicateChecker(session, embedder)
    run_id = new_run_id()
    targets = list(row.targets or [])
    produced = dropped = skipped = first_passed = 0
    skip_notes: list[str] = []
    provider_errors: list[str] = []

    for target in targets:
        # Asked to stop from the Jobs panel: the targets already done are committed.
        raise_if_cancelled(session, row)
        subtopic_id = int(target["subtopic_id"])
        difficulty = Difficulty(target["difficulty"])
        style = library.get(str(target.get("style_id")))
        outcome = "dropped"
        section_id = _section_for(retriever, version, subtopic_id)
        if style is None or section_id is None:
            logger.warning(
                "round %s: dropped subtopic %s/%s: %s",
                round_id,
                subtopic_id,
                difficulty.value,
                "unknown style" if style is None else "no section teaches it",
            )
        else:
            if difficulty is Difficulty.HARD:
                supported, reason = _hard_lesson_supported(
                    session,
                    client,
                    version_id=version_id,
                    question_type=style.question_type.value,
                    section_id=section_id,
                )
                if supported is False:
                    outcome = "skipped"
                    if reason and reason not in skip_notes:
                        skip_notes.append(reason)
                    logger.info(
                        "round %s: skipped hard subtopic %s: %s",
                        round_id,
                        subtopic_id,
                        reason,
                    )
            if outcome != "skipped":
                try:
                    spec = build_question_spec(
                        session,
                        curriculum_version_id=version_id,
                        question_type=style.question_type,
                        difficulty=difficulty,
                        source_section_ids=[section_id],
                        target_subtopic_id=subtopic_id,
                        style_id=style.id,
                    )
                    question = service.generate_round_question(
                        spec,
                        version=version,
                        round_id=round_id,
                        rules=rules,
                        examples=accepted_examples(
                            session,
                            version_id,
                            (subtopic_id, difficulty),
                            style.question_type,
                            section_id=section_id,
                            embedder=embedder,
                        ),
                        run_id=run_id,
                        duplicates=duplicates,
                    )
                    outcome = "produced" if question is not None else "dropped"
                    attempts = question.generation_attempts if question is not None else []
                    if attempts and attempts[0].usable:
                        first_passed += 1
                except InvalidQuestionSpecError as exc:
                    logger.warning("round %s: target refused: %s", round_id, exc.detail)
                except (LLMRequestError, MalformedModelOutputError) as exc:
                    # Questions already committed stay; only the target in flight is lost.
                    session.rollback()
                    provider_errors.append(exc.message)
                    logger.warning("round %s: provider failed: %s", round_id, exc.message)

        if outcome == "produced":
            produced += 1
        elif outcome == "skipped":
            skipped += 1
        else:
            dropped += 1
        rounds.update(
            round_id,
            produced=produced,
            dropped=dropped,
            skipped=skipped,
            skip_reason=_skip_reason(skip_notes),
            first_attempt_passed=first_passed,
        )
        session.commit()

    if produced == 0 and provider_errors:
        raise LLMRequestError(provider_errors[-1], detail="Every target of the round failed.")


def _apply_lessons(
    session: Session, row: GenerationRoundRow, client: StructuredLLMClient | None
) -> None:
    """Learn from the pending reviews of this round's subject, and say so on the round.

    Never raises: a round with stale lessons is still a round, and the error on the row is
    what tells the professor this one was generated without them.
    """
    round_id = row.id
    setup = QuestionSetupRepository(session).get(row.setup_id)
    try:
        run = apply_pending_lessons(
            session,
            round_id=round_id,
            profile=profile_for_version(session, setup.curriculum_version_id),
            client=client,
        )
        applied, error = run.applied, run.error
    except Exception as exc:
        logger.exception("round %s: the lesson run failed", round_id)
        session.rollback()
        applied = 0
        error = (
            exc.message
            if isinstance(exc, AdaptiveTrainerError)
            else f"Lessons were not applied ({type(exc).__name__})."
        )
    GenerationRoundRepository(session).update(
        round_id, lessons_applied=applied, lessons_error=error
    )
    session.commit()


def run_round(
    round_id: int,
    *,
    client: StructuredLLMClient | None = None,
    embedder: Embedder | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Background body: generate every target of a round and record progress.

    Opens its own session (it runs after the request's session is closed). Sets ``RUNNING``
    and ``started_at``; applies the pending review lessons (``lessons_applied`` /
    ``lessons_error``); per target generates -> answer check -> enabled judges -> custom judges
    (``app.evaluation.custom.run_custom_judges``), retrying with the failure reason up to
    ``MAX_GENERATION_ATTEMPTS`` and dropping on final failure. Stored questions carry
    ``style_id``, ``round_id`` and ``target_subtopic_id``. Increments ``produced`` / ``dropped``
    / ``first_attempt_passed`` and commits after each target so polling sees progress. Ends
    ``DONE`` with ``finished_at``, or ``FAILED`` with ``error`` -- never raises out of the task.

    ``client`` / ``embedder`` / ``session_factory`` default to the live ones; tests inject
    fakes. A round that is not ``QUEUED`` is left alone, so a repeated task is harmless.
    """
    if session_factory is None:
        from app.persistence.database import get_session_factory

        session_factory = get_session_factory()
    session = session_factory()
    try:
        rounds = GenerationRoundRepository(session)
        row = rounds.get(round_id)
        if RoundStatus(row.status) is not RoundStatus.QUEUED:
            logger.info("round %s is %s, not queued; not running it", round_id, row.status)
            return
        claimed = session.execute(
            update(GenerationRoundRow)
            .where(
                GenerationRoundRow.id == round_id,
                GenerationRoundRow.status == RoundStatus.QUEUED,
            )
            .values(status=RoundStatus.RUNNING, started_at=datetime.now(UTC))
        )
        if claimed.rowcount != 1:
            session.rollback()
            return
        session.commit()
        _apply_lessons(session, row, client)
        _generate_round(
            session,
            row,
            client=client,
            embedder=embedder if embedder is not None else default_embedder(),
        )
        rounds.update(
            round_id,
            status=RoundStatus.DONE,
            finished_at=datetime.now(UTC),
            drift_warning=check_round_drift(session, row),
        )
        session.commit()
    except JobCancelled:
        session.rollback()
        GenerationRoundRepository(session).update(
            round_id, status=RoundStatus.FAILED, error=CANCELLED, finished_at=datetime.now(UTC)
        )
        session.commit()
        logger.info("round %s cancelled", round_id)
    except Exception as exc:
        logger.exception("round %s failed", round_id)
        session.rollback()
        message = (
            exc.message
            if isinstance(exc, AdaptiveTrainerError)
            else f"Generation stopped unexpectedly ({type(exc).__name__})."
        )
        try:
            GenerationRoundRepository(session).update(
                round_id,
                status=RoundStatus.FAILED,
                error=message,
                finished_at=datetime.now(UTC),
            )
            session.commit()
        except Exception:
            logger.exception("round %s: could not record the failure", round_id)
            session.rollback()
    finally:
        session.close()
