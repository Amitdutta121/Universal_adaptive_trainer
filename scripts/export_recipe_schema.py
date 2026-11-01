r"""Write the JSON Schema of a tutorial recipe file, ``recipes/schema.json``.

    .\.venv\Scripts\python.exe -m scripts.export_recipe_schema           # refresh the file
    .\.venv\Scripts\python.exe -m scripts.export_recipe_schema --check   # fail if it is stale

Generated from ``TutorialRecipe``, the model the loader validates with. ``id`` and ``subject``
come from the file's path, so the schema does not require them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "recipes" / "schema.json"

sys.path.insert(0, str(ROOT))

from app.tutorials.schema import TutorialRecipe  # noqa: E402


def recipe_file_schema() -> str:
    schema = TutorialRecipe.model_json_schema()
    schema["title"] = "Tutorial recipe file"
    schema["required"] = [field for field in schema["required"] if field not in ("id", "subject")]
    return json.dumps(schema, indent=2) + "\n"


def main(argv: list[str]) -> int:
    text = recipe_file_schema()
    if "--check" in argv:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{SCHEMA_PATH} is stale; run: python -m scripts.export_recipe_schema")
            return 1
        return 0
    SCHEMA_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
