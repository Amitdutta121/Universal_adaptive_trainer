"""Per-round drift check: did a lesson bend the questions somewhere no professor asked for?

ADR-063 point 4. Deterministic, no model call, run once a round's questions exist. It looks
for the shapes a bad lesson leaves -- the 16/16 "correct answer is option A" of the
2026-10-08 simulation -- rather than judging quality:

* **Answer position.** Multiple-choice answers all at one index (4 or more), or one index
  holding far more than its share.
* **Option count.** The usual number of options differs from the setup's previous round.
* **Stem length.** The median stem is at least twice, or at most half, the previous round's.

The result is a warning on the round, shown on the round strip. Nothing is blocked: a real
preference can change stem length, and the professor is the one to judge it.
"""

from __future__ import annotations

from collections import Counter
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import QuestionType
from app.persistence.models import GenerationRoundRow, QuestionRow

#: Answers needed before "all at one index" means something (3 in a row happens by chance).
ALL_SAME_MIN = 4
#: With at least this many answers, one index holding ``SKEW_SHARE`` of them is drift.
SKEW_MIN = 6
SKEW_SHARE = 0.6
#: Stems compared by median only when both rounds have at least this many questions.
STEM_MIN = 3
STEM_RATIO = 2.0


def _answer_index(question: QuestionRow) -> tuple[int, int] | None:
    """(correct index, option count) of a well-formed multiple-choice question."""
    content = question.content if isinstance(question.content, dict) else {}
    index, options = content.get("correct_option_index"), content.get("options")
    if (
        question.question_type is not QuestionType.MULTIPLE_CHOICE
        or not isinstance(index, int)
        or isinstance(index, bool)
        or not isinstance(options, list)
        or not 0 <= index < len(options)
    ):
        return None
    return index, len(options)


def _letter(index: int) -> str:
    return chr(ord("A") + index) if index < 26 else str(index)


def drift_warning(questions: list[QuestionRow], previous: list[QuestionRow]) -> str | None:
    """What looks off in ``questions`` (one round) against ``previous`` (the round before)."""
    notes: list[str] = []
    answers = [pair for pair in map(_answer_index, questions) if pair is not None]
    if answers:
        index, count = Counter(index for index, _ in answers).most_common(1)[0]
        if len(answers) >= ALL_SAME_MIN and count == len(answers):
            notes.append(f"all {count} multiple-choice answers are option {_letter(index)}")
        elif len(answers) >= SKEW_MIN and count / len(answers) >= SKEW_SHARE:
            notes.append(
                f"{count} of {len(answers)} multiple-choice answers are option {_letter(index)}"
            )
    before = [pair for pair in map(_answer_index, previous) if pair is not None]
    if answers and before:
        now_options = Counter(n for _, n in answers).most_common(1)[0][0]
        then_options = Counter(n for _, n in before).most_common(1)[0][0]
        if now_options != then_options:
            notes.append(f"options per question changed from {then_options} to {now_options}")
    if len(questions) >= STEM_MIN and len(previous) >= STEM_MIN:
        now_stem = median(len(q.prompt or "") for q in questions)
        then_stem = median(len(q.prompt or "") for q in previous)
        if then_stem and now_stem:
            ratio = now_stem / then_stem
            if ratio >= STEM_RATIO or ratio <= 1 / STEM_RATIO:
                notes.append(
                    f"stems are {ratio:.1f}x the length of last round's "
                    f"({int(now_stem)} vs {int(then_stem)} characters)"
                )
    if not notes:
        return None
    return "Possible drift: " + "; ".join(notes) + "."


def check_round_drift(session: Session, row: GenerationRoundRow) -> str | None:
    """The drift warning for a generated round, against its setup's previous round."""
    previous_id = session.scalar(
        select(GenerationRoundRow.id)
        .where(
            GenerationRoundRow.setup_id == row.setup_id,
            GenerationRoundRow.number < row.number,
        )
        .order_by(GenerationRoundRow.number.desc())
    )

    def questions_of(round_id: int | None) -> list[QuestionRow]:
        if round_id is None:
            return []
        return list(
            session.scalars(
                select(QuestionRow).where(QuestionRow.round_id == round_id).order_by(QuestionRow.id)
            )
        )

    return drift_warning(questions_of(row.id), questions_of(previous_id))
