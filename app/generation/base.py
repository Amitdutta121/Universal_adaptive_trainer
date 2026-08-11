"""Cold-start generator that maps one grounded structured draft to a question."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.domain.enums import GeneratorKind
from app.domain.questions import Question
from app.errors import DomainRuleError, InvalidQuestionSpecError
from app.generation import GeneratorDescriptor
from app.generation.prompts import build_prompt
from app.generation.schemas import (
    RESPONSE_MODEL_FOR,
    build_content,
    prompt_fields_from_draft,
    scoring_kind_for,
)
from app.generation.spec import QuestionSpec, build_question_spec
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.repositories import CurriculumRepository

if TYPE_CHECKING:
    from app.generation import GenerationRequest

DESCRIPTOR = GeneratorDescriptor(kind=GeneratorKind.BASE, name="base", version="1")


class BaseQuestionGenerator:
    """Generate unpersisted textbook-grounded questions from one section each."""

    def __init__(
        self,
        *,
        session: Session | None = None,
        client: StructuredLLMClient | None = None,
        retrieval: SourceRetrieval | None = None,
    ) -> None:
        self._session = session
        self._client = client
        self._retrieval = retrieval or (SourceRetrieval(session) if session is not None else None)
        self._curriculum = CurriculumRepository(session) if session is not None else None

    @property
    def descriptor(self) -> GeneratorDescriptor:
        """Return the stable provenance stamped on generated questions."""
        return DESCRIPTOR

    def generate(self, request: GenerationRequest) -> list[Question]:
        """Generate one unpersisted question for every requested source section.

        ``request.count`` remains part of the selection boundary, but the
        section-first base generator deliberately emits exactly one question per
        source section. Persisting results remains :class:`GenerationService`'s
        responsibility.
        """
        client = self._client or get_structured_client()
        self._client = client
        if self._session is None or self._retrieval is None or self._curriculum is None:
            raise DomainRuleError(
                "BaseQuestionGenerator.generate requires a database session.",
                detail="Construct BaseQuestionGenerator(session=...) to generate questions.",
            )

        version = self._curriculum.get_with_tree(request.curriculum_version_id)
        topic = next(
            (
                candidate
                for candidate in version.topics
                if any(subtopic.id == request.subtopic_id for subtopic in candidate.subtopics)
            ),
            None,
        )
        if topic is None:
            raise InvalidQuestionSpecError(
                "Subtopic is not part of the requested curriculum version.",
                detail=(
                    f"Subtopic {request.subtopic_id} is not in version "
                    f"{request.curriculum_version_id}."
                ),
            )
        subtopic = next(
            candidate for candidate in topic.subtopics if candidate.id == request.subtopic_id
        )

        specs = [
            build_question_spec(
                self._session,
                curriculum_version_id=request.curriculum_version_id,
                topic_id=topic.id,
                subtopic_ids=[request.subtopic_id],
                question_type=request.question_type,
                difficulty=request.difficulty,
                source_section_ids=[section_id],
            )
            for section_id in request.source_section_ids
        ]
        return [
            self.generate_one(spec, topic_name=topic.name, subtopic_names=[subtopic.name])
            for spec in specs
        ]

    def generate_one(
        self,
        spec: QuestionSpec,
        *,
        topic_name: str,
        subtopic_names: list[str],
    ) -> Question:
        """Generate a typed question grounded in the spec's sole source section."""
        if self._retrieval is None:
            raise DomainRuleError(
                "BaseQuestionGenerator.generate_one requires source retrieval.",
                detail="Construct it with session=... or retrieval=....",
            )

        section_id = spec.source_section_ids[0]
        section = self._retrieval.get_section(section_id)
        source = self._retrieval.section_source(section_id)
        citation = source.citation()
        system, prompt = build_prompt(
            spec,
            section_text=section.text,
            citation=citation,
            topic_name=topic_name,
            subtopic_names=subtopic_names,
        )
        client = self._client or get_structured_client()
        draft = client.complete_structured(
            system=system,
            prompt=prompt,
            response_model=RESPONSE_MODEL_FOR[spec.question_type],
        )
        question_prompt, reference_solution, tests = prompt_fields_from_draft(draft)
        return Question(
            curriculum_version_id=spec.curriculum_version_id,
            topic_id=spec.topic_id,
            subtopic_id=spec.subtopic_ids[0],
            kind=scoring_kind_for(spec.question_type),
            question_type=spec.question_type,
            difficulty=spec.difficulty,
            prompt=question_prompt,
            reference_solution=reference_solution,
            tests=tests,
            spec=spec.model_dump(mode="json"),
            content=build_content(
                draft,
                sources=[{"section_id": section_id, "citation": citation}],
                model=client.description,
            ),
            generator_kind=DESCRIPTOR.kind,
            generator_name=DESCRIPTOR.name,
            generator_version=DESCRIPTOR.version,
        )
