"""Judge-prompt overrides and learned generator guidelines are scoped per subject.

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
from app.domain.enums import (
    Difficulty,
    GuidelineStatus,
    JudgeMetricId,
    QuestionType,
    ReviewDecision,
)
from app.errors import NotFoundError
from app.evaluation.judge_prompts import effective_rubric_version, is_edited, resolve_system_prompts
from app.evaluation.prompts import (
    RUBRIC_VERSION,
    SYSTEM_PROMPT_FOR,
    rubric_version_for,
    system_prompts_for,
)
from app.feedback import submit_review
from app.memory import (
    GuidelineEdits,
    GuidelineOperation,
    MemoryGuidelineRepository,
    delete_guideline,
    distill_guidelines,
    generator_target,
)
from app.persistence.models import (
    CourseRow,
    CurriculumVersionRow,
    JudgePromptRow,
    MemoryGuidelineRow,
    QuestionRow,
    TypeInstructionRow,
)
from app.persistence.repositories import (
    JudgePromptRepository,
    QuestionRepository,
    TypeInstructionRepository,
)
from app.personalization import reviews_for_type
from app.subjects import PYTHON_PROFILE, profile_for

#: Storage key -> the profile of a course on that subject (no course id: presets are shared).
PROFILES = {
    LEGACY_SUBJECT: PYTHON_PROFILE,
    "physics": profile_for(SimpleNamespace(name="Physics", subject="physics", question_types=None)),
}

PHYSICS = "physics"
METRIC = JudgeMetricId.ISSUES
MC = QuestionType.MULTIPLE_CHOICE


class DistillerClient:
    """Adds one guideline citing every review it is shown; records the prompts."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []

    @property
    def description(self) -> str:
        return "fake/distiller"

    def complete_structured(self, *, system: str, prompt: str, response_model: type[BaseModel]):
        self.prompts.append(prompt)
        ids = [int(part.split(",")[0]) for part in prompt.split('"review_id": ')[1:]]
        return GuidelineEdits(
            operations=[GuidelineOperation(op="add", text=self.text, review_ids=ids)]
        )


TARGET = generator_target(MC)


def _review_of(question: QuestionRow) -> int:
    return question.reviews[-1].id


def _distill(session: Session, subject: str, review_ids: list[int], client: Any):
    result = distill_guidelines(
        session,
        target=TARGET,
        subject=subject,
        question_type=MC,
        review_ids=review_ids,
        client=client,
    )
    session.commit()
    return result


def _guideline(subject: str) -> MemoryGuidelineRow:
    return MemoryGuidelineRow(
        target=TARGET,
        subject=subject,
        text="One",
        review_ids=[1, 2],
        status=GuidelineStatus.ACTIVE,
        confirmed_by_professor=False,
    )


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
    def test_a_learned_guideline_never_reaches_another_subject(
        self, session: Session, owner: str, other: str
    ) -> None:
        review = _review_of(_reviewed_question(session, subject=owner, comment="Too long."))

        result = _distill(session, owner, [review], DistillerClient("Keep options short."))

        repository = MemoryGuidelineRepository(session)
        (row,) = repository.list_for(subject=owner, statuses=list(GuidelineStatus))
        assert (row.id, row.subject, row.target) == (result.added[0], owner, TARGET)
        assert repository.list_for(subject=other, statuses=list(GuidelineStatus)) == []

    def test_reviews_are_evidence_only_for_their_own_subject(self, session: Session) -> None:
        physics = _reviewed_question(session, subject=PHYSICS, comment="PHYSICS COMPLAINT")
        python = _reviewed_question(session, subject=LEGACY_SUBJECT, comment="PYTHON COMPLAINT")
        # No course at all: built before courses existed, so it is legacy evidence.
        old = _reviewed_question(session, subject=None, comment="OLD COMPLAINT")

        python_reviews = {r.comment for r in reviews_for_type(session, MC)}
        physics_reviews = {r.comment for r in reviews_for_type(session, MC, subject=PHYSICS)}
        assert python_reviews == {"PYTHON COMPLAINT", "OLD COMPLAINT"}
        assert physics_reviews == {"PHYSICS COMPLAINT"}

        client = DistillerClient("R")
        ids = [_review_of(row) for row in (physics, python, old)]
        _distill(session, PHYSICS, ids, client)
        assert "PHYSICS COMPLAINT" in client.prompts[0]
        assert "PYTHON COMPLAINT" not in client.prompts[0]
        assert "OLD COMPLAINT" not in client.prompts[0]

    def test_a_subject_with_no_reviews_learns_nothing(self, session: Session) -> None:
        python = _reviewed_question(session, subject=LEGACY_SUBJECT, comment="PYTHON COMPLAINT")
        client = DistillerClient("Never reached.")

        result = _distill(session, PHYSICS, [_review_of(python)], client)

        assert not result.changed
        assert client.prompts == []

    def test_deleting_a_guideline_touches_only_its_subject(self, session: Session) -> None:
        repository = MemoryGuidelineRepository(session)
        mine = repository.add(_guideline(LEGACY_SUBJECT))
        theirs = repository.add(_guideline(PHYSICS))
        session.commit()

        with pytest.raises(NotFoundError):
            delete_guideline(session, mine.id, subject=PHYSICS)
        delete_guideline(session, theirs.id, subject=PHYSICS)

        assert theirs.status is GuidelineStatus.RETIRED
        assert mine.status is GuidelineStatus.ACTIVE

    def test_uniqueness_is_per_subject_and_type(self, session: Session) -> None:
        session.add(TypeInstructionRow(subject=PHYSICS, question_type=MC, instruction="A"))
        session.add(TypeInstructionRow(subject=LEGACY_SUBJECT, question_type=MC, instruction="B"))
        session.commit()
        session.add(TypeInstructionRow(subject=PHYSICS, question_type=MC, instruction="C"))
        with pytest.raises(IntegrityError):
            session.commit()
