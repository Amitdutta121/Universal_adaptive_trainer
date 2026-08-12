"""Display helpers in the web layer.

``fenced_segments`` exists because multiple-choice and true/false drafts have no
``code`` field, so a code-reading question arrives with the snippet fenced inside
the prompt. These tests pin the display contract, not the generation one.
"""

from __future__ import annotations

import pytest

from app.web.templating import fenced_segments


def test_plain_prose_is_one_text_segment() -> None:
    assert fenced_segments("What does this do?") == [("text", "What does this do?")]


def test_a_fenced_block_becomes_a_code_segment() -> None:
    prompt = "What does this do?\n\n```python\nage = 25\n```"

    assert fenced_segments(prompt) == [("text", "What does this do?"), ("code", "age = 25")]


def test_the_language_tag_is_dropped() -> None:
    assert fenced_segments("```python\nx = 1\n```") == [("code", "x = 1")]


def test_a_fence_with_no_language_tag_keeps_every_line() -> None:
    assert fenced_segments("```\nx = 1\ny = 2\n```") == [("code", "x = 1\ny = 2")]


def test_indentation_inside_a_block_survives() -> None:
    """A snippet may open with an indented line; losing it changes the question."""
    prompt = "```python\nfor i in range(3):\n    print(i)\n```"

    assert fenced_segments(prompt) == [("code", "for i in range(3):\n    print(i)")]


def test_text_after_a_block_is_kept() -> None:
    prompt = "Before.\n```\nx = 1\n```\nAfter."

    assert fenced_segments(prompt) == [
        ("text", "Before."),
        ("code", "x = 1"),
        ("text", "After."),
    ]


def test_several_blocks_alternate() -> None:
    prompt = "A\n```\none\n```\nB\n```\ntwo\n```"

    assert [kind for kind, _ in fenced_segments(prompt)] == ["text", "code", "text", "code"]


def test_an_unbalanced_fence_is_shown_as_written() -> None:
    """Guessing where a malformed block ends could hide part of the question."""
    prompt = "What does this do?\n```python\nage = 25"

    assert fenced_segments(prompt) == [("text", prompt)]


def test_an_empty_block_is_dropped() -> None:
    assert fenced_segments("Only prose.\n```\n```") == [("text", "Only prose.")]


@pytest.mark.parametrize("value", [None, "", "   "])
def test_nothing_to_show_yields_no_segments(value: str | None) -> None:
    assert fenced_segments(value) == []


def test_a_first_line_that_is_code_is_not_mistaken_for_a_language_tag() -> None:
    """``x=1`` is not a bare word, so it must survive as the first line."""
    assert fenced_segments("```\nx=1\ny=2\n```") == [("code", "x=1\ny=2")]
