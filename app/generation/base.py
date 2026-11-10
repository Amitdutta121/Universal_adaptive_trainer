"""Cold-start generator that maps one grounded structured draft to a question."""

from __future__ import annotations

from dataclasses import dataclass
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
    RoundExamples,
    base_type_instruction,
    build_prompt,
    instruction_fingerprint,
    render_round_target,
    render_taxonomy,
)
from app.generation.schemas import (
    MultipleChoiceDraft,
    TaxonomyClaim,
    build_content,
    prompt_fields_from_draft,
    response_model_for,
    scoring_kind_for,
    shuffle_options,
)
from app.generation.spec import (
    QuestionSpec,
    TaxonomyClaimOutcome,
    build_question_spec,
    require_approved_version,
)
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient, get_structured_client
from app.memory import active_guidelines, generator_target, render_with_guidelines
from app.persistence.models import CourseRow, CurriculumVersionRow
from app.question_types.output_prediction import observed_expected_output
from app.subjects import PYTHON_PROFILE, SubjectProfile, profile_for_course_id

if TYPE_CHECKING:
    from app.generation import GenerationRequest
    from app.styles.schema import QuestionStyle

DESCRIPTOR = GeneratorDescriptor(kind=GeneratorKind.BASE, name="base", version="1")


@dataclass(frozen=True)
class PreparedPrompt:
    """What one question is asked with (:meth:`BaseQuestionGenerator.prepare`)."""

    system: str
    prompt: str
    #: The grounding stored on the question's ``content["sources"]``.
    sources: list[dict[str, object]]
    #: The style the spec names, ``None`` without one.
    style: QuestionStyle | None
    #: Which instruction wrote the question (ADR-040), stored as ``personalization_context``.
    instruction_stamp: dict[str, object]


class BaseQuestionGenerator:
    """Generate unpersisted textbook-grounded questions from one chunk each."""

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
        """The instruction to send, and the stamp naming it (ADR-033, ADR-040, ADR-063).

        The shipped instruction plus this subject's **active** guidelines for the type
        (:mod:`app.memory`); pending ones are not sent. Read per generation rather than
        cached, so a lesson run or a professor's confirm takes effect on the next question.

        Returns the rendered text, or ``None`` for the shipped text alone, plus a record of
        which one was used. The stamp fingerprints the text that will actually be sent and
        names the guidelines in it: a question generated before a guideline changed must
        not later appear to have used the newer instruction.
        """
        guidelines = (
            active_guidelines(
                self._session,
                target=generator_target(question_type),
                subject=profile.personal_key,
            )
            if self._session is not None
            else []
        )
        base = base_type_instruction(question_type)
        effective = render_with_guidelines(base, [row.text for row in guidelines])
        stamp = {
            "type_instruction": {
                "source": "learned" if guidelines else "shipped",
                "fingerprint": instruction_fingerprint(effective),
                "rule_count": len(guidelines),
                "guideline_ids": [row.id for row in guidelines],
                "review_count": len(
                    {review for row in guidelines for review in row.review_ids or []}
                ),
            }
        }
        return (effective if guidelines else None), stamp

    def generate(self, request: GenerationRequest) -> list[Question]:
        """Generate one unpersisted question for every requested source chunk.

        ``request.count`` remains part of the selection boundary, but the
        chunk-first base generator deliberately emits exactly one question per
        source chunk. Persisting results remains :class:`GenerationService`'s
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
                source_chunk_ids=[chunk_id],
            )
            for chunk_id in request.source_chunk_ids
        ]
        return [self.generate_one(spec, version=version) for spec in specs]

    def generate_one(
        self,
        spec: QuestionSpec,
        *,
        version: CurriculumVersionRow,
        instructor_feedback: str | None = None,
        review: QuestionReview | None = None,
        examples: RoundExamples | None = None,
        follow_up: str | None = None,
        max_attempts: int = MAX_GENERATION_ATTEMPTS,
    ) -> Question:
        """Generate a typed question grounded in the spec's sole source chunk.

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
        and the ``examples`` retrieved for it (:class:`RoundExamples`) to the prompt;
        ``review`` judges each clean attempt inside the retry loop
        (:func:`generate_with_retries`). Both are unused on a chunk-only spec.

        Raises:
            DomainRuleError: the spec's style has a computed figure; its questions are
                written by a program (``app.generation.computed.generate_computed_question``).
        """
        prepared = self.prepare(
            spec,
            version=version,
            instructor_feedback=instructor_feedback,
            examples=examples,
            follow_up=follow_up,
        )
        style = prepared.style
        if style is not None and style.figure == "computed":
            raise DomainRuleError(
                "A computed-figure style is generated by its program.",
                detail=f"Style {style.id} goes through generate_computed_question.",
            )
        sources = prepared.sources
        client = self._client or get_structured_client()

        def build(draft: TaxonomyClaim, outcome: TaxonomyClaimOutcome) -> Question:
            if isinstance(draft, MultipleChoiceDraft):
                # Before any check sees it: the model's own answer position is not random.
                draft = shuffle_options(draft)
            question_prompt, reference_solution, tests = prompt_fields_from_draft(draft)
            content = build_content(draft, sources=sources, model=client.description)
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
                personalization_context=prepared.instruction_stamp,
            )

        question, _attempts = generate_with_retries(
            client,
            system=prepared.system,
            prompt=prepared.prompt,
            # A diagram or chart style's draft must carry that figure (ADR-080); the validator's
            # ``figure_drawable`` check sends a figure that cannot be drawn back for repair.
            response_model=response_model_for(spec.question_type, style),
            version=version,
            build_question=build,
            validator=self._validator,
            review=review,
            max_attempts=max_attempts,
        )
        return question

    def prepare(
        self,
        spec: QuestionSpec,
        *,
        version: CurriculumVersionRow,
        instructor_feedback: str | None = None,
        examples: RoundExamples | None = None,
        follow_up: str | None = None,
    ) -> PreparedPrompt:
        """The prompts one question of ``spec`` is asked with, and what they rest on.

        Shared by :meth:`generate_one` and computed-figure generation
        (``app.generation.computed``), so both ask from the same grounding, style and
        learned instruction.
        """
        if self._retrieval is None:
            raise DomainRuleError(
                "BaseQuestionGenerator.prepare requires source retrieval.",
                detail="Construct it with session=... or retrieval=....",
            )
        chunk_id = spec.source_chunk_ids[0]
        chunk = self._retrieval.get_chunk(chunk_id)
        citation = chunk.citation()
        # The course's subject decides the system text and whose learned instruction applies.
        profile = self._profile(version)
        type_instruction, instruction_stamp = self._type_instruction(spec.question_type, profile)
        style = self._style(spec, profile, version)
        target_block = (
            self._round_target(spec, version, examples, style) if spec.is_round_spec else None
        )
        system, prompt = build_prompt(
            spec,
            section_text=chunk.text,
            citation=citation,
            taxonomy=render_taxonomy(version),
            type_instruction=type_instruction,
            instructor_feedback=instructor_feedback,
            profile=profile,
            target_block=target_block,
            follow_up=follow_up,
        )
        return PreparedPrompt(
            system=system,
            prompt=prompt,
            sources=[{"chunk_id": chunk_id, "citation": citation}],
            style=style,
            instruction_stamp=instruction_stamp,
        )

    def style_for(self, spec: QuestionSpec, version: CurriculumVersionRow) -> QuestionStyle | None:
        """The style ``spec`` names, from its course's styles; ``None`` without one."""
        return self._style(spec, self._profile(version), version)

    def _profile(self, version: CurriculumVersionRow) -> SubjectProfile:
        if self._session is None:
            return PYTHON_PROFILE
        return profile_for_course_id(self._session, version.course_id)

    def _style(
        self, spec: QuestionSpec, profile: SubjectProfile, version: CurriculumVersionRow
    ) -> QuestionStyle | None:
        """The style the spec names, from the course's styles; ``None`` without one.

        A course with figures turned off gets every style as text only (ADR-080).
        """
        if not spec.style_id or self._session is None:
            return None
        from app.styles import styles_for

        style = next(
            (row for row in styles_for(self._session, profile) if row.id == spec.style_id),
            None,
        )
        if style is None or style.figure == "none":
            return style
        course = self._session.get(CourseRow, version.course_id)
        if course is None or course.figures_enabled:
            return style
        return style.model_copy(
            update={
                "figure": "none",
                "examples": tuple(
                    example.model_copy(update={"figure": None}) for example in style.examples
                ),
            }
        )

    def _round_target(
        self,
        spec: QuestionSpec,
        version: CurriculumVersionRow,
        examples: RoundExamples | None,
        style: QuestionStyle | None,
    ) -> str:
        """The target block of a round spec: subtopic, library style, accepted examples."""
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
        return render_round_target(
            subtopic=subtopic,
            topic_name=topic.name,
            style=style,
            examples=examples,
            facet=spec.facet,
        )
