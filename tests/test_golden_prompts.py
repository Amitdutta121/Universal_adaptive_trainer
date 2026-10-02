"""Phase 2 gate (S0): the Python course's prompts stay byte-identical to the golden file.

The golden file was captured from the code before any phase-2 change. A failure here means a
refactor changed what the model is told; refresh the file (``scripts/show_prompts.py --write``)
only when that change is deliberate.
"""

from __future__ import annotations

import json

import pytest

from scripts.show_prompts import GOLDEN, collect_prompts

GOLDEN_PROMPTS: dict[str, str] = json.loads(GOLDEN.read_text(encoding="utf-8"))
CURRENT = collect_prompts()


def test_no_prompt_was_added_or_removed() -> None:
    assert sorted(CURRENT) == sorted(GOLDEN_PROMPTS)


@pytest.mark.parametrize("name", sorted(GOLDEN_PROMPTS))
def test_prompt_is_unchanged(name: str) -> None:
    assert CURRENT.get(name) == GOLDEN_PROMPTS[name], name
