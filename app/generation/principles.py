"""Shared grounding rules for structured base-question generation."""

from __future__ import annotations

COMMON_SYSTEM = """You create one accurate introductory-Python assessment question.
Ground the assessed skill in the supplied textbook section. You may use fresh
variable names, literals, and examples, but do not assess an untaught Python
feature or claim the section says something it does not. Keep the requested
difficulty within the taught skill. Return only the requested structured fields;
ensure the reference answer, explanation, and any tests agree with the question."""
