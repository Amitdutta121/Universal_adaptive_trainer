"""Personalized generator that augments base prompts with professor context."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.domain.enums import GeneratorKind
from app.domain.questions import Question
from app.errors import DomainRuleError
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
from app.persistence.repositories import PreferenceRepository
from app.personalization.context import (
    MAX_PREFS_IN_PROMPT,
    SOFT_PREF_FLOOR,
    STYLE_PEDAGOGY_DISCLAIMER,
    build_personalization_prompt_blocks,
    transparency_payload,
)
from app.personalization.embeddings import Embedder
from app.personalization.retrieval import retrieve_examples

if TYPE_CHECKING:
    pass

DESCRIPTOR = GeneratorDescriptor(
    kind=GeneratorKind.PERSONALIZED,
    name="personalized-context",
    version="1",
)


class PersonalizedContextGenerator:
    """Generate textbook-grounded questions with retrieved review context."""

    def __init__(
        self,
        *,
        session: Session | None = None,
        client: StructuredLLMClient | None = None,
        retrieval: SourceRetrieval | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._session = session
        self._client = client
        self._retrieval = retrieval or (SourceRetrieval(session) if session is not None else None)
        self._embedder = embedder

    @property
    def descriptor(self) -> GeneratorDescriptor:
        return DESCRIPTOR

    def generate_one(
        self,
        spec: QuestionSpec,
        *,
        topic_name: str,
        subtopic_names: list[str],
    ) -> Question:
        """Generate one question with personalized prompt context."""
        if self._session is None or self._retrieval is None:
            raise DomainRuleError(
                "PersonalizedContextGenerator.generate_one requires a database session.",
                detail="Construct PersonalizedContextGenerator(session=...) to generate questions.",
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

        retrieval = retrieve_examples(
            self._session,
            spec=spec,
            topic_id=spec.topic_id,
            topic_name=topic_name,
            subtopic_names=subtopic_names,
            citation=citation,
            embedder=self._embedder,
        )
        preferences = PreferenceRepository(self._session).list_for_generation(
            soft_floor=SOFT_PREF_FLOOR,
        )
        personalization = build_personalization_prompt_blocks(
            preferences=preferences,
            retrieval=retrieval,
        )
        if personalization:
            prompt = f"{prompt}\n\n{personalization}"
        system = f"{system}\n\n{STYLE_PEDAGOGY_DISCLAIMER}"

        client = self._client or get_structured_client()
        draft = client.complete_structured(
            system=system,
            prompt=prompt,
            response_model=RESPONSE_MODEL_FOR[spec.question_type],
        )
        question_prompt, reference_solution, tests = prompt_fields_from_draft(draft)
        review_ids = [
            example.review_id for example in (*retrieval.approved_or_edited, *retrieval.rejected)
        ]
        preference_ids = [
            pref.id for pref in preferences[:MAX_PREFS_IN_PROMPT] if pref.id is not None
        ]
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
            personalization_context_json=transparency_payload(
                preference_ids=preference_ids,
                review_ids=review_ids,
            ),
        )
