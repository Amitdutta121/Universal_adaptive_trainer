"""Cold-start generator that maps one grounded structured draft to a question."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.enums import GeneratorKind
from app.domain.questions import Question
from app.generation import GeneratorDescriptor
from app.generation.prompts import build_prompt
from app.generation.schemas import (
    RESPONSE_MODEL_FOR,
    encode_content,
    prompt_fields_from_draft,
    scoring_kind_for,
)
from app.generation.spec import QuestionSpec
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client

if TYPE_CHECKING:
    from app.generation import GenerationRequest

DESCRIPTOR = GeneratorDescriptor(kind=GeneratorKind.BASE, name="base", version="1")


class BaseQuestionGenerator:
    """Generate one textbook-grounded question for one validated section spec."""

    def __init__(
        self,
        *,
        client: StructuredLLMClient | None = None,
        retrieval: SourceRetrieval | None = None,
    ) -> None:
        self._client = client
        self._retrieval = retrieval

    @property
    def descriptor(self) -> GeneratorDescriptor:
        """Return the stable provenance stamped on generated questions."""
        return DESCRIPTOR

    def generate(self, request: GenerationRequest) -> list[Question]:
        """Check lazy LLM configuration for the legacy generator-selection seam.

        A legacy request omits the topic name needed for a grounded prompt and
        cannot carry a database session. Persisted section-first generation is
        therefore deliberately performed by :class:`GenerationService`.
        """
        del request
        if self._client is None:
            get_structured_client()
        raise RuntimeError("Use GenerationService to generate persisted section-first questions.")

    def generate_one(
        self,
        spec: QuestionSpec,
        *,
        topic_name: str,
        subtopic_names: list[str],
    ) -> Question:
        """Generate a typed question grounded in the spec's sole source section."""
        if self._retrieval is None:
            raise RuntimeError(
                "BaseQuestionGenerator needs SourceRetrieval to generate a question."
            )
        if len(spec.source_section_ids) != 1:
            raise ValueError(
                "BaseQuestionGenerator generates exactly one question per source section."
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
            spec_json=spec.model_dump_json(),
            content_json=encode_content(
                draft,
                sources=[{"section_id": section_id, "citation": citation}],
                model=client.description,
            ),
            generator_kind=DESCRIPTOR.kind,
            generator_name=DESCRIPTOR.name,
            generator_version=DESCRIPTOR.version,
        )
