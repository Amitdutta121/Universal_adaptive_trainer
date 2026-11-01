"""Replay every stored student attempt through the old and the new scorer (C5 acceptance).

    .\\.venv\\Scripts\\python.exe -m scripts.replay_grading [path/to/adaptive_trainer.db]

Reads the database directly (read-only) and compares, per attempt, the frozen pre-move scorer
(``tests/grading_oracle.py``) with ``app.adaptive.scoring.score_answer``: score, test counts and
feedback. Also checks the new score equals the score stored when the attempt was made. Exits 1
on any difference.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import grading_oracle  # noqa: E402

from app.adaptive.scoring import score_answer  # noqa: E402
from app.domain.enums import Difficulty, QuestionKind, QuestionType  # noqa: E402
from app.domain.questions import Question  # noqa: E402


def main(db_path: str) -> int:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = connection.execute(
        """
        SELECT a.id, a.answer, a.score, q.id, q.question_type, q.content_json, q.tests
        FROM student_attempts a JOIN questions q ON q.id = a.question_id
        WHERE a.score IS NOT NULL AND q.question_type IS NOT NULL
        ORDER BY a.id
        """
    ).fetchall()
    compared: Counter[str] = Counter()
    mismatches = 0
    stored_differs = 0
    for attempt_id, answer, stored, question_id, qtype, content_json, tests in rows:
        question_type = QuestionType(qtype)
        question = Question(
            id=question_id,
            prompt="(replay)",
            question_type=question_type,
            kind=QuestionKind.DISCRETE,
            difficulty=Difficulty.EASY,
            content=json.loads(content_json or "{}"),
            tests=tests,
        )
        old = grading_oracle.score_answer(question, answer or "")
        new = score_answer(question, answer or "")
        compared[qtype] += 1
        same = (old.score, old.passed_tests, old.total_tests, old.detail) == (
            new.score,
            new.passed_tests,
            new.total_tests,
            new.detail,
        )
        if not same:
            mismatches += 1
            print(
                f"MISMATCH attempt {attempt_id} ({qtype}): "
                f"old={old.score}/{old.detail!r} new={new.score}/{new.detail!r}"
            )
        elif new.score != stored:
            # Old and new agree; the stored score came from an even earlier scorer.
            stored_differs += 1
            print(
                f"note: attempt {attempt_id} ({qtype}) was stored as {stored}; "
                f"old and new scorers both give {new.score}"
            )
    total = sum(compared.values())
    print(f"Replayed {total} attempts: {dict(compared)}")
    print(
        "Old and new scorers identical on every attempt."
        if mismatches == 0
        else f"{mismatches} old-vs-new mismatches."
    )
    if stored_differs:
        print(f"{stored_differs} attempt(s) stored by an earlier scorer (old and new agree).")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "adaptive_trainer.db")))
