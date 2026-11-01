"""Per-recipe stats, and the weights they give the composer (Phase 6, Task 28).

Two stored signals per recipe, both within one course (a course's stats are its own data,
like everything else in it):

- **approval rate** -- the professors' decisions (``tutorial_recipe_decisions``): approved
  taxonomies over decided ones;
- **next-attempt correctness** -- of the blocks shown to students (``tutorial_block_views``),
  how often the student's next answer in that subtopic was right.

Each is smoothed toward 1/2 (one success and one failure assumed), and the weight is their
product scaled so an unknown recipe weighs 1.0. Once a recipe has enough evidence and either
rate is below :data:`MIN_RATE`, its weight is 0 and the composer no longer chooses it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.persistence.models import (
    CurriculumVersionRow,
    QuestionSetVersionRow,
    StudentAttemptRow,
    TrainingSessionRow,
    TutorialBlockRow,
    TutorialBlockViewRow,
    TutorialRecipeDecisionRow,
)

#: Below this raw rate, with enough evidence, a recipe is no longer chosen.
MIN_RATE = 0.25
#: Decisions, and shown blocks with an outcome, needed before :data:`MIN_RATE` applies.
MIN_DECISIONS = 4
MIN_OUTCOMES = 20


@dataclass(frozen=True)
class RecipeStats:
    recipe_id: str
    decided: int = 0
    approved: int = 0
    #: Blocks shown whose next answer is known.
    outcomes: int = 0
    next_correct: int = 0

    @property
    def approval_rate(self) -> float | None:
        return self.approved / self.decided if self.decided else None

    @property
    def next_correct_rate(self) -> float | None:
        return self.next_correct / self.outcomes if self.outcomes else None

    @property
    def weight(self) -> float:
        approval = self.approval_rate
        correct = self.next_correct_rate
        if self.decided >= MIN_DECISIONS and approval is not None and approval < MIN_RATE:
            return 0.0
        if self.outcomes >= MIN_OUTCOMES and correct is not None and correct < MIN_RATE:
            return 0.0
        smoothed_approval = (self.approved + 1) / (self.decided + 2)
        smoothed_correct = (self.next_correct + 1) / (self.outcomes + 2)
        return 4 * smoothed_approval * smoothed_correct


def _in_course(course_id: int | None):
    column = CurriculumVersionRow.course_id
    return column.is_(None) if course_id is None else column == course_id


def recipe_stats(session: Session, course_id: int | None) -> dict[str, RecipeStats]:
    """Stats of every recipe with a decision or a shown block in the course."""
    decided = {
        recipe_id: (total, approved)
        for recipe_id, total, approved in session.execute(
            select(
                TutorialRecipeDecisionRow.recipe_id,
                func.count(),
                func.sum(case((TutorialRecipeDecisionRow.approved, 1), else_=0)),
            )
            .join(
                CurriculumVersionRow,
                CurriculumVersionRow.id == TutorialRecipeDecisionRow.curriculum_version_id,
            )
            .where(_in_course(course_id))
            .group_by(TutorialRecipeDecisionRow.recipe_id)
        )
    }
    shown = {
        recipe_id: (total, correct)
        for recipe_id, total, correct in session.execute(
            select(
                TutorialBlockViewRow.recipe_id,
                func.count(),
                func.sum(case((TutorialBlockViewRow.next_correct, 1), else_=0)),
            )
            .join(TrainingSessionRow, TrainingSessionRow.id == TutorialBlockViewRow.session_id)
            .join(
                QuestionSetVersionRow,
                QuestionSetVersionRow.id == TrainingSessionRow.set_version_id,
            )
            .join(
                CurriculumVersionRow,
                CurriculumVersionRow.id == QuestionSetVersionRow.curriculum_version_id,
            )
            .where(TutorialBlockViewRow.next_correct.is_not(None), _in_course(course_id))
            .group_by(TutorialBlockViewRow.recipe_id)
        )
    }
    return {
        recipe_id: RecipeStats(
            recipe_id=recipe_id,
            decided=decided.get(recipe_id, (0, 0))[0],
            approved=int(decided.get(recipe_id, (0, 0))[1] or 0),
            outcomes=shown.get(recipe_id, (0, 0))[0],
            next_correct=int(shown.get(recipe_id, (0, 0))[1] or 0),
        )
        for recipe_id in sorted(decided.keys() | shown.keys())
    }


def recipe_weights(session: Session, course_id: int | None) -> dict[str, float]:
    """``recipe_id -> weight`` for the composer; a recipe missing here weighs 1.0."""
    return {
        recipe_id: stats.weight for recipe_id, stats in recipe_stats(session, course_id).items()
    }


def record_views(
    session: Session,
    attempt: StudentAttemptRow,
    blocks: list[TutorialBlockRow],
    *,
    moment: str,
) -> None:
    """Log the blocks shown with an attempt; showing the same ones again logs nothing. Flushes."""
    seen = set(
        session.scalars(
            select(TutorialBlockViewRow.block_id).where(
                TutorialBlockViewRow.attempt_id == attempt.id,
                TutorialBlockViewRow.moment == moment,
            )
        )
    )
    for block in blocks:
        if block.id in seen:
            continue
        session.add(
            TutorialBlockViewRow(
                attempt_id=attempt.id,
                session_id=attempt.session_id,
                block_id=block.id,
                recipe_id=block.recipe_id,
                subtopic_id=block.subtopic_id,
                moment=moment,
            )
        )
    session.flush()


def record_outcome(session: Session, attempt: StudentAttemptRow, *, correct: bool) -> None:
    """Fill ``next_correct`` of the views this answer is the next attempt for. Flushes.

    That is the attempt's own pre-teaching, and every earlier result-card view in the run for
    the same subtopic still waiting for one.
    """
    if attempt.subtopic_id is None:
        return
    waiting = TutorialBlockViewRow.next_correct.is_(None)
    session.execute(
        update(TutorialBlockViewRow)
        .where(
            waiting,
            TutorialBlockViewRow.attempt_id == attempt.id,
            TutorialBlockViewRow.moment == "before",
        )
        .values(next_correct=correct)
    )
    session.execute(
        update(TutorialBlockViewRow)
        .where(
            waiting,
            TutorialBlockViewRow.session_id == attempt.session_id,
            TutorialBlockViewRow.subtopic_id == attempt.subtopic_id,
            TutorialBlockViewRow.moment == "after",
            TutorialBlockViewRow.attempt_id != attempt.id,
        )
        .values(next_correct=correct)
    )
    session.flush()
