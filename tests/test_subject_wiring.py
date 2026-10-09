"""Phase 2, S3: the course's subject reaches generation, judging and personalization.

A recording fake LLM shows what each call was told: a Physics course's generator and judges get
the Physics prompts, a course-less (legacy) one gets the golden Python text, and what was learned
or edited for one subject never reaches another.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import book_documents as docs
from llm_fakes import MetricJudgeClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, GuidelineStatus, JudgeMetricId, QuestionType
from app.domain.questions import Question
from app.evaluation.prompts import SYSTEM_PROMPT_FOR, rubric_version_for, system_prompt_for
from app.evaluation.service import PedagogicalJudge
from app.generation.base import BaseQuestionGenerator
from app.generation.principles import COMMON_SYSTEM, common_system
from app.generation.schemas import MultipleChoiceDraft
from app.generation.spec import build_question_spec
from app.ingestion import BookImportService
from app.persistence.models import CourseRow, MemoryGuidelineRow
from app.persistence.repositories import JudgePromptRepository
from app.subjects import PYTHON_PROFILE, profile_for, profile_for_course_id
from tests.conftest import TEST_PROFESSOR_ID

TAXONOMY = (
    b'{"schema_version":"1","label":"Mechanics","topics":['
    b'{"name":"Motion","subtopics":[{"name":"Free fall"},{"name":"Velocity"}]}]}'
)


class Recorder(MetricJudgeClient):
    """Records the system prompt of every call, generation and judging alike."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.systems: list[str] = []

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        self.systems.append(system)
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kwargs
        )


def _course(session: Session, subject: str | None, types: list[str] | None) -> int | None:
    if subject is None:
        return None
    course = CourseRow(
        name=f"{subject} course",
        subject=subject,
        question_types=types,
        owner_id=TEST_PROFESSOR_ID,
    )
    session.add(course)
    session.flush()
    return course.id


def _generate(session: Session, settings, course_id: int | None) -> tuple[Recorder, Question]:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.think_python()), course_id=course_id
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json", data=TAXONOMY, course_id=course_id
    )
    session.commit()
    topic = version.topics[0]
    section_id = book.chapters[0].sections[0].id
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )
    client = Recorder(
        draft=MultipleChoiceDraft(
            topic_id=topic.id,
            subtopic_ids=[topic.subtopics[0].id],
            prompt="A ball is dropped. What is its acceleration?",
            options=["g downwards", "zero", "g upwards"],
            correct_option_index=0,
            explanation="Free fall.",
        )
    )
    question = BaseQuestionGenerator(session=session, client=client).generate_one(
        spec, version=version
    )
    return client, question


def test_a_physics_course_generates_with_the_physics_system_prompt(session, settings) -> None:
    course_id = _course(session, "physics", ["multiple_choice", "numeric_response"])
    client, _ = _generate(session, settings, course_id)
    physics = profile_for_course_id(session, course_id)

    system = client.generation_calls[0]["system"]
    assert system == common_system(physics)
    assert system != COMMON_SYSTEM
    assert "python" not in system.lower()


def test_a_course_less_taxonomy_still_gets_the_golden_python_prompt(session, settings) -> None:
    client, _ = _generate(session, settings, None)
    assert client.generation_calls[0]["system"] == COMMON_SYSTEM


def test_a_learned_instruction_reaches_only_its_own_subject(session, settings) -> None:
    physics_course = _course(session, "physics", None)
    session.add(
        MemoryGuidelineRow(
            target="generator:multiple_choice",
            # The course's owner's own Physics guidelines (ADR-059).
            subject=profile_for_course_id(session, physics_course).personal_key,
            text="PHYSICS-ONLY RULE",
            review_ids=[1, 2],
            status=GuidelineStatus.ACTIVE,
            confirmed_by_professor=False,
        )
    )
    session.commit()
    physics_client, _ = _generate(session, settings, physics_course)
    python_client, _ = _generate(session, settings, None)

    assert "PHYSICS-ONLY RULE" in physics_client.generation_calls[0]["prompt"]
    assert "PHYSICS-ONLY RULE" not in python_client.generation_calls[0]["prompt"]


def test_the_judges_use_the_question_courses_panel(session, settings) -> None:
    course_id = _course(session, "physics", ["multiple_choice"])
    _, question = _generate(session, settings, course_id)
    physics = profile_for_course_id(session, course_id)
    JudgePromptRepository(session).save(
        JudgeMetricId.ISSUES, subject="intro_python", system_prompt="PYTHON EDIT", note=None
    )
    session.commit()

    client = Recorder()
    evaluation = PedagogicalJudge(session, client=client).evaluate(question)

    assert system_prompt_for(JudgeMetricId.ISSUES, physics) in client.systems
    assert "PYTHON EDIT" not in client.systems
    assert SYSTEM_PROMPT_FOR[JudgeMetricId.ISSUES] not in client.systems
    assert evaluation.rubric_version == rubric_version_for(physics)
    assert evaluation.rubric_version != rubric_version_for(PYTHON_PROFILE)


def test_two_custom_courses_keep_separate_personalization() -> None:
    llms = profile_for(SimpleNamespace(id=1, name="LLMs", subject="custom", question_types=None))
    art = profile_for(SimpleNamespace(id=2, name="Art", subject="custom", question_types=None))
    physics_a = profile_for(SimpleNamespace(id=3, name="A", subject="physics", question_types=None))
    physics_b = profile_for(SimpleNamespace(id=4, name="B", subject="physics", question_types=None))

    assert llms.storage_key == "custom:1" and art.storage_key == "custom:2"
    # A preset is shared: every Physics course learns from every Physics course.
    assert physics_a.storage_key == physics_b.storage_key == "physics"
    assert PYTHON_PROFILE.storage_key == "intro_python"
