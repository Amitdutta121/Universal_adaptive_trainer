"""The professor-facing navigation.

Single source of truth: the sidebar, the dashboard cards and the navigation test
all read this list, so a new section cannot appear in one place and be missing
from another.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavSection:
    """One top-level application section."""

    key: str
    label: str
    path: str
    summary: str


NAV_SECTIONS: tuple[NavSection, ...] = (
    NavSection(
        key="books",
        label="Books",
        path="/books",
        summary="Upload introductory Python textbooks and inspect their extracted structure.",
    ),
    NavSection(
        key="curriculum",
        label="Curriculum",
        path="/curriculum",
        summary="Upload a fixed Topic → Subtopic taxonomy JSON for adaptive training.",
    ),
    NavSection(
        key="questions",
        label="Questions",
        path="/questions",
        summary="Generate, validate and review Python assessment questions.",
    ),
    NavSection(
        key="feedback",
        label="Professor Feedback",
        path="/feedback",
        summary="The approve / reject / edit history that teaches the generator your preferences.",
    ),
    NavSection(
        key="instructions",
        label="Instructions",
        path="/instructions",
        summary="What the generator is told for each question type, learned from your reviews.",
    ),
    NavSection(
        key="judges",
        label="Judges",
        path="/judges",
        summary="The four advisory reviewers, and the prompt each one follows.",
    ),
    NavSection(
        key="coverage",
        label="Coverage",
        path="/coverage",
        summary="Whether the approved questions cover every subtopic at every difficulty.",
    ),
    NavSection(
        key="students",
        label="Students",
        path="/students",
        summary="Adaptive training progress: BKT topic mastery and subtopic weakness.",
    ),
)

SECTIONS_BY_KEY: dict[str, NavSection] = {section.key: section for section in NAV_SECTIONS}
