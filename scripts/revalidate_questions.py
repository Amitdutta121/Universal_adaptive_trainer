"""Re-validate every stored question with the pre-move runner and the current one (C5 acceptance).

    .\\.venv\\Scripts\\python.exe -m scripts.revalidate_questions [path/to/adaptive_trainer.db]

Reads the database read-only and runs each question's type checks twice: with the frozen runner
(``tests/frozen_runner.py``, its own subprocess) and with ``app.validation.runner`` (the graders'
shared executor). Reports must be identical apart from temporary folder names. Exits 1 if not.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import frozen_runner  # noqa: E402

from app.domain.enums import QuestionType  # noqa: E402
from app.validation.runner import LocalCodeRunner  # noqa: E402
from app.validation.type_checks import check_type  # noqa: E402

_TEMP_DIR = re.compile(r"tmp[a-z0-9_]{6,}", re.IGNORECASE)


def _report(question_type: QuestionType, content: dict, runner: object) -> list[str]:
    question = SimpleNamespace(question_type=question_type)
    return [_TEMP_DIR.sub("tmp", repr(c)) for c in check_type(question, content, runner)]


def main(db_path: str) -> int:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT id, question_type, content_json FROM questions WHERE question_type IS NOT NULL"
    ).fetchall()
    differences = 0
    for question_id, question_type, content_json in rows:
        content = json.loads(content_json or "{}")
        old = _report(QuestionType(question_type), content, frozen_runner.LocalCodeRunner())
        new = _report(QuestionType(question_type), content, LocalCodeRunner())
        if old != new:
            differences += 1
            print(f"DIFF question {question_id} ({question_type}):\n  old={old}\n  new={new}")
    print(f"Re-validated {len(rows)} stored questions: {differences} report differences.")
    return 0 if differences == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "adaptive_trainer.db")))
