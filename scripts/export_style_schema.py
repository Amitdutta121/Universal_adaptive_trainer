"""Write the JSON Schema of a style file, ``styles/schema.json``.

    .\\.venv\\Scripts\\python.exe -m scripts.export_style_schema           # refresh the file
    .\\.venv\\Scripts\\python.exe -m scripts.export_style_schema --check   # fail if it is stale

Generated from ``QuestionStyle``, the model the loader validates with, so the two cannot
disagree. ``id`` and ``subject`` are optional in a file (they come from its path), so the
schema does not require them. Editors that understand JSON Schema can validate a style file
with a first line ``# yaml-language-server: $schema=../schema.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "styles" / "schema.json"

sys.path.insert(0, str(ROOT))

from app.styles.schema import QuestionStyle  # noqa: E402


def style_file_schema() -> str:
    schema = QuestionStyle.model_json_schema()
    schema["title"] = "Question style file"
    schema["required"] = [field for field in schema["required"] if field not in ("id", "subject")]
    return json.dumps(schema, indent=2) + "\n"


def main(argv: list[str]) -> int:
    text = style_file_schema()
    if "--check" in argv:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{SCHEMA_PATH} is stale; run: python -m scripts.export_style_schema")
            return 1
        return 0
    SCHEMA_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
