"""Cold-start generator that maps one grounded structured draft to a question."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.domain.enums import GeneratorKind, QuestionType
from app.domain.questions import Question
from app.errors import DomainRuleError
from app.generation import GeneratorDescriptor
from app.generation.attempts import (
    MAX_GENERATION_ATTEMPTS,
    QuestionReview,
    QuestionValidator,
    generate_with_retries,
)
from app.generation.prompts import (
    base_type_instruction,
    build_prompt,
    instruction_fingerprint,
    render_round_target,
    render_taxonomy,
)
from app.generation.schemas import (
    TaxonomyClaim,
    build_content,
    prompt_fields_from_draft,
    response_model_for,
    scoring_kind_for,
)
from app.generation.spec import (
    QuestionSpec,
    TaxonomyClaimOutcome,
    build_question_spec,
    require_approved_version,
)
from app.question_types.output_prediction import observed_expected_output
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import CurriculumVersionRow
from app.persistence.repositories import TypeInstructionRepository
from app.subjects import PYTHON_PROFILE, SubjectProfile, profile_for_course_id

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
        self, question_type: QuestionType, profile: SubjectProfile = PYTHON_PROFILE
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
            TypeInstructionRepository(self._session).get(
                question_type, subject=profile.personal_key
            )
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

    def generate_one(
        self,
        spec: QuestionSpec,
        *,
        version: CurriculumVersionRow,
        instructor_feedback: str | None = None,
        review: QuestionReview | None = None,
        examples: list[str] | None = None,
        follow_up: str | None = None,
        max_attempts: int = MAX_GENERATION_ATTEMPTS,
    ) -> Question:
        """Generate a typed question grounded in the spec's sole source section.

        A classification the approved tree refuses is retried with the violation
        stated, and the question is returned either way (ADR-032). It carries the
        attempts that produced it, so the refusal reaches the professor as
        evidence instead of ending the run. The claim is never repaired here:
        guessing which subtopic the model meant would put an invented tag on a
        question and hide the miss from the subtopic judge that exists to catch
        exactly this.

        ``instructor_feedback`` is forwarded to :func:`build_prompt` when an
        instructor asked for a new version of an existing question.

        A round spec (``spec.target_subtopic_id`` set) adds the target subtopic, its style
        and up to a few accepted ``examples`` to the prompt; ``review`` judges each clean
        attempt inside the retry loop (:func:`generate_with_retries`). Both are unused on a
        section-only spec.
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
        # The course's subject decides the system text and whose learned instruction applies.
        profile = (
            profile_for_course_id(self._session, version.course_id)
            if self._session is not None
            else PYTHON_PROFILE
        )
        type_instruction, instruction_stamp = self._type_instruction(spec.question_type, profile)
        target_block = (
            self._round_target(spec, version, profile, examples) if spec.is_round_spec else None
        )
        system, prompt = build_prompt(
            spec,
            section_text=section.text,
            citation=citation,
            taxonomy=render_taxonomy(version),
            type_instruction=type_instruction,
            instructor_feedback=instructor_feedback,
            profile=profile,
            target_block=target_block,
            follow_up=follow_up,
        )
        client = self._client or get_structured_client()

        def build(draft: TaxonomyClaim, outcome: TaxonomyClaimOutcome) -> Question:
            question_prompt, reference_solution, tests = prompt_fields_from_draft(draft)
            content = build_content(
                draft,
                sources=[{"section_id": section_id, "citation": citation}],
                model=client.description,
            )
            if spec.question_type is QuestionType.OUTPUT_PREDICTION:
                code = content.get("code")
                observed = observed_expected_output(code) if isinstance(code, str) else None
                if observed is not None:
                    content["expected_output"] = observed
                    reference_solution = observed
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
                spec=spec.stored(),
                content=content,
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
            response_model=response_model_for(spec.question_type),
            version=version,
            build_question=build,
            validator=self._validator,
            review=review,
            max_attempts=max_attempts,
        )
        return question

    @staticmethod
    def _round_target(
        spec: QuestionSpec,
        version: CurriculumVersionRow,
        profile: SubjectProfile,
        examples: list[str] | None,
    ) -> str:
        """The target block of a round spec: subtopic, library style, accepted examples."""
        from app.styles import get_library

        found = next(
            (
                (topic, subtopic)
                for topic in version.topics
                for subtopic in topic.subtopics
                if subtopic.id == spec.target_subtopic_id
            ),
            None,
        )
        if found is None:
            raise DomainRuleError(
                "The target subtopic is not part of this taxonomy.",
                detail=f"Subtopic {spec.target_subtopic_id} is not in version {version.id}.",
            )
        topic, subtopic = found
        style = (
            next(
                (row for row in get_library(profile.personal_key) if row.id == spec.style_id),
                None,
            )
            if spec.style_id
            else None
        )
        return render_round_target(
            subtopic=subtopic, topic_name=topic.name, style=style, examples=examples
        )
