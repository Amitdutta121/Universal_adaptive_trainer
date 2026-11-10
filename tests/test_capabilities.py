"""The boundary of what can be made for a course, as the drafter and the agent read it (ADR-077)."""

from __future__ import annotations

from app.assessment import catalog
from app.curriculum.capabilities import capabilities_text
from app.curriculum.drafting import DRAFT_SYSTEM_PROMPT, DraftBrief, draft_user_prompt
from app.domain.enums import TutorialRenderer


def test_the_boundary_lists_every_offerable_type_and_every_renderer() -> None:
    text = capabilities_text()
    for spec in catalog.QUESTION_TYPES:
        assert (spec.label in text) == catalog.is_offerable(spec.id), spec.id
    assert len(list(TutorialRenderer)) <= text.count("\n- ")
    # New recipes and styles can be made; only their parts are fixed.
    assert "can be drafted at any time" in text
    assert "Outside the boundary" in text


def test_the_boundary_names_no_subject() -> None:
    text = capabilities_text().lower()
    for subject in ("unity", "game", "biology", "physics", "statistics"):
        assert subject not in text


def test_the_drafter_is_given_the_boundary_and_told_to_list_what_is_outside() -> None:
    prompt = draft_user_prompt(DraftBrief(title="Any course", description="Anything."))
    assert prompt.startswith(capabilities_text())
    assert "out_of_scope" in DRAFT_SYSTEM_PROMPT
