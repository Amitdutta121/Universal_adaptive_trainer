"""Judge-prompt overrides and learned type instructions are scoped per subject.

A rule learned in a Python course must never reach a Physics course, and the
other way round. Every caller that names no subject gets the legacy subject,
which is exactly today's behaviour.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assessment.catalog import LEGACY_SUBJECT
from app.domain.enums import Difficulty, JudgeMetricId, QuestionType, ReviewDecision
from app.evaluation.judge_prompts import effective_rubric_version, is_edited, resolve_system_prompts
from app.evaluation.prompts import (
    RUBRIC_VERSION,
    SYSTEM_PROMPT_FOR,
    rubric_version_for,
    system_prompts_for,
)
from app.feedback import submit_review
from app.persistence.models import (
    CourseRow,
    CurriculumVersionRow,
    JudgePromptRow,
    QuestionRow,
    TypeInstructionRow,
)
from app.persistence.repositories import (
    JudgePromptRepository,
    QuestionRepository,
    TypeInstructionRepository,
)
from app.personalization import (
    LearnedRule,
    LearnedRules,
    delete_type_instruction_rule,
    refresh_type_instruction,
    reviews_for_type,
)
from app.subjects import PYTHON_PROFILE, profile_for

#: Storage key -> the profile of a course on that subject (no course id: presets are shared).
PROFILES = {
    LEGACY_SUBJECT: PYTHON_PROFILE,
    "physics": profile_for(SimpleNamespace(name="Physics", subject="physics", question_types=None)),
}

PHYSICS = "physics"
METRIC = JudgeMetricId.ISSUES
MC = QuestionType.MULTIPLE_CHOICE


class RewriterClient:
    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self.rules = rules
        self.prompts: list[str] = []

    @property
    def description(self) -> str:
        return "fake/rewriter"

    def complete_structured(self, *, system: str, prompt: str, response_model: type[BaseModel]):
        self.prompts.append(prompt)
        return LearnedRules(rules=[LearnedRule(**rule) for rule in self.rules])


def _reviewed_question(session: Session, *, subject: str | None, comment: str) -> QuestionRow:
    """A reviewed multiple-choice question in a course of ``subject`` (``None``: no course)."""
    version_id = None
    if subject is not None:
        course = CourseRow(name=f"{subject} course", subject=subject)
        session.add(course)
        session.flush()
        version = CurriculumVersionRow(course_id=course.id, label=f"{subject} taxonomy")
        session.add(version)
        session.flush()
        version_id = version.id
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt=f"A {subject} question?",
            original_prompt=f"A {subject} question?",
            question_type=MC,
            difficulty=Difficulty.MEDIUM,
            curriculum_version_id=version_id,
        )
    )
    session.commit()
    submit_review(
        session,
        question_id=row.id,
        decision=ReviewDecision.EDIT,
        comment=comment,
        prompt="Edited.",
        reference_solution="",
        tests="",
    )
    session.commit()
    return row


class TestJudgePrompts:
    def test_defaults_are_unchanged_for_the_legacy_subject(self, session: Session) -> None:
        assert effective_rubric_version(session) == RUBRIC_VERSION
        assert effective_rubric_version(session, profile=PYTHON_PROFILE) == RUBRIC_VERSION
        assert resolve_system_prompts(session) == dict(SYSTEM_PROMPT_FOR)

    def test_an_override_without_a_subject_is_stored_as_the_legacy_subject(
        self, session: Session
    ) -> None:
        row = JudgePromptRepository(session).save(METRIC, system_prompt="EDITED", note=None)
        session.commit()
        assert row.subject == LEGACY_SUBJECT

    @pytest.mark.parametrize(
        ("owner", "other"), [(LEGACY_SUBJECT, PHYSICS), (PHYSICS, LEGACY_SUBJECT)]
    )
    def test_an_override_never_reaches_another_subject(
        self, session: Session, owner: str, other: str
    ) -> None:
        repository = JudgePromptRepository(session)
        repository.save(METRIC, subject=owner, system_prompt="EDITED", note=None)
        session.commit()

        assert repository.get(METRIC, subject=owner) is not None
        assert repository.get(METRIC, subject=other) is None
        assert repository.list_all(subject=other) == []
        mine, theirs = PROFILES[owner], PROFILES[other]
        assert resolve_system_prompts(session, profile=mine)[METRIC] == "EDITED"
        assert resolve_system_prompts(session, profile=theirs) == system_prompts_for(theirs)
        assert effective_rubric_version(session, profile=mine) != rubric_version_for(mine)
        assert effective_rubric_version(session, profile=theirs) == rubric_version_for(theirs)
        assert is_edited(session, METRIC, profile=mine)
        assert not is_edited(session, METRIC, profile=theirs)

    def test_each_subject_keeps_its_own_revision_and_delete(self, session: Session) -> None:
        repository = JudgePromptRepository(session)
        repository.save(METRIC, system_prompt="PY 1", note=None)
        repository.save(METRIC, system_prompt="PY 2", note=None)
        physics = repository.save(METRIC, subject=PHYSICS, system_prompt="PHYS", note=None)
        session.commit()

        assert physics.revision == 1
        assert repository.get(METRIC).revision == 2
        assert repository.delete(METRIC, subject=PHYSICS)
        assert repository.get(METRIC, subject=PHYSICS) is None
        assert repository.get(METRIC).system_prompt == "PY 2"

    def test_uniqueness_is_per_subject_and_metric(self, session: Session) -> None:
        session.add(JudgePromptRow(subject=PHYSICS, metric=METRIC, system_prompt="A"))
        session.add(JudgePromptRow(subject=LEGACY_SUBJECT, metric=METRIC, system_prompt="B"))
        session.commit()
        session.add(JudgePromptRow(subject=PHYSICS, metric=METRIC, system_prompt="C"))
        with pytest.raises(IntegrityError):
            session.commit()


class TestTypeInstructions:
    def test_an_instruction_without_a_subject_is_stored_as_the_legacy_subject(
        self, session: Session
    ) -> None:
        row = TypeInstructionRepository(session).upsert(
            MC, instruction="I", rules=[], review_count=0
        )
        session.commit()
        assert row.subject == LEGACY_SUBJECT

    @pytest.mark.parametrize(
        ("owner", "other"), [(LEGACY_SUBJECT, PHYSICS), (PHYSICS, LEGACY_SUBJECT)]
    )
    def test_a_learned_instruction_never_reaches_another_subject(
        self, session: Session, owner: str, other: str
    ) -> None:
        _reviewed_question(session, subject=owner, comment="Too long.")
        client = RewriterClient([{"rule": "Keep options short.", "review_ids": [1]}])

        row = refresh_type_instruction(
            session, MC, base_instruction="BASE", client=client, subject=owner
        )

        repository = TypeInstructionRepository(session)
        assert row is not None and row.subject == owner
        assert repository.get(MC, subject=owner) is not None
        assert repository.get(MC, subject=other) is None
        assert repository.list_all(subject=other) == []

    def test_reviews_are_evidence_only_for_their_own_subject(self, session: Session) -> None:
        _reviewed_question(session, subject=PHYSICS, comment="PHYSICS COMPLAINT")
        _reviewed_question(session, subject=LEGACY_SUBJECT, comment="PYTHON COMPLAINT")
        # No course at all: built before courses existed, so it is legacy evidence.
        _reviewed_question(session, subject=None, comment="OLD COMPLAINT")

        python = {r.comment for r in reviews_for_type(session, MC)}
        physics = {r.comment for r in reviews_for_type(session, MC, subject=PHYSICS)}
        assert python == {"PYTHON COMPLAINT", "OLD COMPLAINT"}
        assert physics == {"PHYSICS COMPLAINT"}

        client = RewriterClient([{"rule": "R", "review_ids": []}])
        refresh_type_instruction(session, MC, base_instruction="B", client=client, subject=PHYSICS)
        assert "PHYSICS COMPLAINT" in client.prompts[0]
        assert "PYTHON COMPLAINT" not in client.prompts[0]

    def test_a_subject_with_no_reviews_learns_nothing(self, session: Session) -> None:
        _reviewed_question(session, subject=LEGACY_SUBJECT, comment="PYTHON COMPLAINT")
        client = RewriterClient([{"rule": "Never reached.", "review_ids": []}])

        assert (
            refresh_type_instruction(
                session, MC, base_instruction="B", client=client, subject=PHYSICS
            )
            is None
        )
        assert client.prompts == []

    def test_deleting_a_rule_touches_only_its_subject(self, session: Session) -> None:
        repository = TypeInstructionRepository(session)
        rules = [{"rule": "One", "review_ids": []}, {"rule": "Two", "review_ids": []}]
        repository.upsert(MC, instruction="PY", rules=rules, review_count=1)
        repository.upsert(MC, subject=PHYSICS, instruction="PH", rules=rules, review_count=1)
        session.commit()

        delete_type_instruction_rule(
            session, MC, rule_index=0, base_instruction="BASE", subject=PHYSICS
        )

        assert [r["rule"] for r in repository.get(MC, subject=PHYSICS).rules] == ["Two"]
        assert [r["rule"] for r in repository.get(MC).rules] == ["One", "Two"]

    def test_uniqueness_is_per_subject_and_type(self, session: Session) -> None:
        session.add(TypeInstructionRow(subject=PHYSICS, question_type=MC, instruction="A"))
        session.add(TypeInstructionRow(subject=LEGACY_SUBJECT, question_type=MC, instruction="B"))
        session.commit()
        session.add(TypeInstructionRow(subject=PHYSICS, question_type=MC, instruction="C"))
        with pytest.raises(IntegrityError):
            session.commit()
