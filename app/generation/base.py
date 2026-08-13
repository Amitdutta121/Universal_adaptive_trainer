"""Cold-start generator that maps one grounded structured draft to a question."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.domain.enums import GeneratorKind
from app.domain.questions import Question
from app.errors import DomainRuleError
from app.generation import GeneratorDescriptor
from app.generation.prompts import build_prompt, render_taxonomy
from app.generation.schemas import (
    RESPONSE_MODEL_FOR,
    build_content,
    prompt_fields_from_draft,
    scoring_kind_for,
)
from app.generation.spec import (
    QuestionSpec,
    build_question_spec,
    require_approved_version,
    resolve_claimed_taxonomy,
)
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import CurriculumVersionRow

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
        if self._session is None or self._retrieval is None:
            raise DomainRuleError(
                "BaseQuestionGenerator.generate requires a database session.",
                detail="Construct BaseQuestionGenerator(session=...) to generate questions.",
            )

        version = require_approved_version(self._session, request.curriculum_version_id)
        specs = [
            build_question_spec(
                self._session,
                curriculum_version_id=request.curriculum_version_id,
                question_type=request.question_type,
                difficulty=request.difficulty,
                source_section_ids=[section_id],
            )
            for section_id in request.source_section_ids
        ]
        return [self.generate_one(spec, version=version) for spec in specs]

    def generate_one(self, spec: QuestionSpec, *, version: CurriculumVersionRow) -> Question:
        """Generate a typed question grounded in the spec's sole source section.

        Raises:
            InvalidQuestionSpecError: the model classified its question under a
                topic or subtopic that is not in ``version``. Recorded as a
                failure rather than repaired: guessing which subtopic it meant
                would put an invented tag on a question and hide the miss from
                the subtopic judge that exists to catch exactly this.
        """
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
            taxonomy=render_taxonomy(version),
        )
        client = self._client or get_structured_client()
        draft = client.complete_structured(
            system=system,
            prompt=prompt,
            response_model=RESPONSE_MODEL_FOR[spec.question_type],
        )
        claim = resolve_claimed_taxonomy(
            version, topic_id=draft.topic_id, subtopic_ids=draft.subtopic_ids
        )
        question_prompt, reference_solution, tests = prompt_fields_from_draft(draft)
        return Question(
            curriculum_version_id=spec.curriculum_version_id,
            topic_id=claim.topic_id,
            subtopic_ids=claim.subtopic_ids,
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
