"""Generation rounds of a question setup: pick targets, generate in the background.

Phase 0 contract (docs/QUESTION_SETUP_PLAN.md, agent B): fixed signatures, no behaviour yet.
The setup routes (agent A) call :func:`start_round`; the rounds route calls
:func:`next_round`; both hand :func:`run_round` to a background task after the request
commits, and the client polls ``GET /api/rounds/{id}``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.persistence.models import GenerationRoundRow

#: Questions per round unless the caller asks otherwise.
DEFAULT_ROUND_SIZE = 10


def start_round(
    session: Session, setup_id: int, *, size: int = DEFAULT_ROUND_SIZE
) -> GenerationRoundRow:
    """Create round 1 of a freshly saved setup, ``QUEUED``, with its targets chosen.

    Same selection as :func:`next_round`; separate so the setup route's intent is explicit and
    so it can refuse a setup that already has rounds. Flushes, does not commit, and does not
    generate: the caller commits and schedules ``run_round(row.id)``.

    Raises:
        NotFoundError: the setup does not exist.
        DomainRuleError: the setup already has a round.
    """
    raise NotImplementedError("app.generation.rounds.start_round is a Phase 0 stub")


def next_round(
    session: Session, setup_id: int, *, size: int = DEFAULT_ROUND_SIZE
) -> GenerationRoundRow:
    """Create the next round of a setup, ``QUEUED``, targeting cells still below target.

    Picks up to ``size`` targets ``{"subtopic_id", "difficulty", "style_id"}`` from cells whose
    approved + pending count is below the setup's ``cell_targets``; the style per cell is drawn
    by weight (each reject of that style in that cell halves it; two rejects exclude it).
    ``requested`` is the number of targets, which may be fewer than ``size`` (zero when every
    cell is full). Flushes, does not commit, does not generate.

    Raises:
        NotFoundError: the setup does not exist.
        DomainRuleError: a round of this setup is still ``QUEUED`` or ``RUNNING``.
    """
    raise NotImplementedError("app.generation.rounds.next_round is a Phase 0 stub")


def run_round(round_id: int) -> None:
    """Background body: generate every target of a round and record progress.

    Opens its own session (it runs after the request's session is closed). Sets ``RUNNING``
    and ``started_at``; per target generates -> answer check -> enabled judges -> custom judges
    (``app.evaluation.custom.run_custom_judges``), retrying with the failure reason up to
    ``MAX_GENERATION_ATTEMPTS`` and dropping on final failure. Stored questions carry
    ``style_id``, ``round_id`` and ``target_subtopic_id``. Increments ``produced`` / ``dropped``
    and commits after each target so polling sees progress. Ends ``DONE`` with
    ``finished_at``, or ``FAILED`` with ``error`` -- never raises out of the task.
    """
    raise NotImplementedError("app.generation.rounds.run_round is a Phase 0 stub")
