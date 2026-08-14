"""Cold-start generator that maps one grounded structured draft to a question."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.domain.enums import GeneratorKind, QuestionType
from app.domain.questions import Question
from app.errors import DomainRuleError
from app.generation import GeneratorDescriptor
from app.generation.attempts import QuestionValidator, generate_with_retries
from app.generation.prompts import (
    base_type_instruction,
    build_prompt,
    instruction_fingerprint,
    render_taxonomy,
)
from app.generation.schemas import (
    RESPONSE_MODEL_FOR,
    TaxonomyClaim,
    build_content,
    prompt_fields_from_draft,
    scoring_kind_for,
)
from app.generation.spec import (
    QuestionSpec,
    TaxonomyClaimOutcome,
    build_question_spec,
    require_approved_version,
)
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import CurriculumVersionRow
from app.persistence.repositories import TypeInstructionRepository

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
        validator: QuestionValidator | None = None,
    ) -> None:
        self._session = session
        self._client = client
        self._retrieval = retrieval or (SourceRetrieval(session) if session is not None else None)
        #: Injected rather than imported, so generation does not depend on
        #: validation. Without one, only the taxonomy claim triggers a retry.
        self._validator = validator

    @property
    def descriptor(self) -> GeneratorDescriptor:
        """Return the stable provenance stamped on generated questions."""
        return DESCRIPTOR

    def _type_instruction(
        self, question_type: QuestionType
    ) -> tuple[str | None, dict[str, object]]:
        """The instruction to send, and the stamp naming it (ADR-033, ADR-040).

        Read per generation rather than cached, so a refresh takes effect on the
        next question instead of the next process.

        Returns the learned override or ``None`` for the shipped text, plus a
        record of which one was used. The stamp fingerprints the text that will
        actually be sent, not the row it came from: what a question was generated
        from is the only thing worth recording, and a question generated before a
        refresh must not later appear to have used the newer instruction.
        """
        row = (
            TypeInstructionRepository(self._session).get(question_type)
            if self._session is not None
            else None
        )
        effective = row.instruction if row is not None else base_type_instruction(question_type)
        stamp = {
            "type_instruction": {
                "source": "learned" if row is not None else "shipped",
                "fingerprint": instruction_fingerprint(effective),
                "rule_count": len(row.rules or []) if row is not None else 0,
                "review_count": row.review_count if row is not None else 0,
            }
        }
        return (row.instruction if row is not None else None), stamp

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

        A classification the approved tree refuses is retried with the violation
        stated, and the question is returned either way (ADR-032). It carries the
        attempts that produced it, so the refusal reaches the professor as
        evidence instead of ending the run. The claim is never repaired here:
        guessing which subtopic the model meant would put an invented tag on a
        question and hide the miss from the subtopic judge that exists to catch
        exactly this.
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
        type_instruction, instruction_stamp = self._type_instruction(spec.question_type)
        system, prompt = build_prompt(
            spec,
            section_text=section.text,
            citation=citation,
            taxonomy=render_taxonomy(version),
            type_instruction=type_instruction,
        )
        client = self._client or get_structured_client()

        def build(draft: TaxonomyClaim, outcome: TaxonomyClaimOutcome) -> Question:
            question_prompt, reference_solution, tests = prompt_fields_from_draft(draft)
            return Question(
                curriculum_version_id=spec.curriculum_version_id,
                topic_id=outcome.storable_topic_id,
                subtopic_ids=outcome.storable_subtopic_ids,
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
                # Which instruction wrote this question (ADR-040). ``base@1``
                # names the code path only; every question is personalized, so
                # the descriptor alone cannot distinguish two of them.
                personalization_context=instruction_stamp,
            )

        question, _attempts = generate_with_retries(
            client,
            system=system,
            prompt=prompt,
            response_model=RESPONSE_MODEL_FOR[spec.question_type],
            version=version,
            build_question=build,
            validator=self._validator,
        )
        return question
