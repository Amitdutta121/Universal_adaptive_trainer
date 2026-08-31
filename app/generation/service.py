"""Section-first orchestration for question generation and persistence.

One generator, not two. Personalization is the per-type instruction the
generator already reads (ADR-033), so there is no longer a "personalized"
variant to choose between: every question is generated with whatever has been
learned for its type.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, EvaluationTrigger, QuestionType
from app.domain.questions import Question
from app.errors import InvalidQuestionSpecError
from app.evaluation import PedagogicalJudge, new_run_id, record_evaluation, skipped_evaluation
from app.generation.base import BaseQuestionGenerator
from app.generation.batch import ChunkQuestionRequest, compile_chunk_requests
from app.generation.spec import QuestionSpec, build_question_spec, require_approved_version
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient
from app.persistence.models import CurriculumVersionRow, QuestionRow
from app.persistence.repositories import QuestionRepository, _source_section_ids


class GenerationService:
    """Validate a section set, generate one question per section, and store it."""

    def __init__(
        self,
        session: Session,
        *,
        client: StructuredLLMClient | None = None,
    ) -> None:
        from app.validation import get_question_validator

        self._session = session
        self._retrieval = SourceRetrieval(session)
        # Handed to the generator so a failed check triggers a retry inside the
        # generation loop, rather than being discovered after it has returned
        # (ADR-032).
        self._validator = get_question_validator(session)
        self._generator = BaseQuestionGenerator(
            session=session,
            client=client,
            retrieval=self._retrieval,
            validator=self._validator,
        )
        self._judge = PedagogicalJudge(session, client=client)
        self._questions = QuestionRepository(session)

    def generate_for_sections(
        self,
        *,
        curriculum_version_id: int,
        question_type: QuestionType,
        difficulty: Difficulty,
        source_section_ids: list[int] | None = None,
        book_id: int | None = None,
        seed: str | None = None,
    ) -> list[QuestionRow]:
        """Generate and persist one question for each explicit or book section.

        All specs are validated before the first model call, so a bad id later in
        the selection costs nothing rather than being discovered mid-run. The
        topic and subtopics each question carries come back from the generator,
        not from this call.

        Each section commits on its own. A partly finished batch is therefore a
        real outcome: if the provider fails on the fourth of six sections, three
        questions are kept and the caller sees the error (ADR-032).
        """
        section_ids = self._resolve_section_ids(source_section_ids, book_id)
        version = require_approved_version(self._session, curriculum_version_id)
        specs = [
            build_question_spec(
                self._session,
                curriculum_version_id=curriculum_version_id,
                question_type=question_type,
                difficulty=difficulty,
                source_section_ids=[section_id],
                seed=seed,
            )
            for section_id in section_ids
        ]
        return self._generate_specs(specs, version=version)

    def generate_batch(
        self,
        *,
        curriculum_version_id: int,
        chunks: Sequence[ChunkQuestionRequest],
        seed: str | None = None,
    ) -> list[QuestionRow]:
        """Generate the questions a per-chunk spec sheet asks for (ADR-044).

        Unlike :meth:`generate_for_sections`, one chunk may produce several
        questions, at several difficulties, in several formats. The compiler
        decides which format each question gets; this method only turns the
        compiled plan into specs and runs it.

        The whole batch shares one run id, so the questions a professor asked for
        in one submission stay attributable to it. Every other property of a run
        is unchanged: each question commits on its own, so a provider failure
        part-way through keeps what has already been paid for.
        """
        planned = compile_chunk_requests(chunks)
        version = require_approved_version(self._session, curriculum_version_id)
        specs = [
            build_question_spec(
                self._session,
                curriculum_version_id=curriculum_version_id,
                question_type=question.question_type,
                difficulty=question.difficulty,
                source_section_ids=[question.section_id],
                seed=seed,
            )
            for question in planned
        ]
        return self._generate_specs(specs, version=version)

    def regenerate_from_question(
        self,
        question_id: int,
        *,
        feedback: str,
        professor_id: int | None = None,
    ) -> QuestionRow:
        """Generate a NEW question from the same inputs as an existing one.

        The instructor feedback is threaded into the generation prompt. The
        source question is never modified -- this is a fresh row with its own
        attempts, validation report and evaluation, linked back to the source
        for provenance (ADR-002 keeps generated originals immutable, and an
        instructor rewrite is a new question, not an edit of the old one).

        This path deliberately writes no ``ProfessorReviewRow`` and triggers no
        instruction or judge relearn: those belong to the review flow in
        :mod:`app.web.routes.api.feedback`, not here.

        ``professor_id`` is accepted for parity with the review endpoint but is
        not used to switch generators.
        """
        source = self._questions.get(question_id)
        spec = self._spec_from_row(source)
        version = require_approved_version(self._session, spec.curriculum_version_id)
        rows = self._generate_specs([spec], version=version, instructor_feedback=feedback)
        new_row = rows[0]
        new_row.regenerated_from_question_id = source.id
        new_row.regeneration_feedback = feedback
        self._session.commit()
        return new_row

    def _spec_from_row(self, row: QuestionRow) -> QuestionSpec:
        """Rebuild the generation spec for an existing question.

        Prefers the frozen ``spec_json``; falls back to the section ids recorded
        in ``content["sources"]`` for rows written before specs were stored. The
        rebuilt spec is re-validated through :func:`build_question_spec` so a
        since-deleted section or a curriculum that is no longer approved is
        reported before any model call.
        """
        if row.question_type is None:
            raise InvalidQuestionSpecError(
                "This question has no recorded type.",
                detail="Generate a fresh question instead of regenerating this one.",
            )
        if row.curriculum_version_id is None:
            raise InvalidQuestionSpecError(
                "This question is not grounded in a curriculum version.",
                detail="Generate a fresh question instead of regenerating this one.",
            )
        section_ids = _source_section_ids(row)
        if len(section_ids) != 1:
            raise InvalidQuestionSpecError(
                "Cannot recover a single source section for this question.",
                detail=f"Recovered section ids: {section_ids or 'none'}.",
            )
        seed = (row.spec or {}).get("seed")
        return build_question_spec(
            self._session,
            curriculum_version_id=row.curriculum_version_id,
            question_type=row.question_type,
            difficulty=row.difficulty,
            source_section_ids=section_ids,
            seed=seed if isinstance(seed, str) else None,
        )

    def _generate_specs(
        self,
        specs: list[QuestionSpec],
        *,
        version: CurriculumVersionRow,
        instructor_feedback: str | None = None,
    ) -> list[QuestionRow]:
        """Generate, validate, judge and persist one question per spec.

        One run id groups the questions generated by this call, so a generated
        evaluation is as attributable to a run as a re-run one is (ADR-030).

        ``instructor_feedback`` is set only by :meth:`regenerate_from_question`
        and is forwarded verbatim to the generator; the section-first callers
        leave it ``None``.
        """
        run_id = new_run_id()
        rows = []
        for spec in specs:
            # The generator validated every attempt and carries the report for the
            # one it settled on, so there is nothing left to check here.
            question = self._generator.generate_one(
                spec, version=version, instructor_feedback=instructor_feedback
            )
            row = self._questions.add(self._row_from_question(question))
            report = question.validation_report or self._validator.validate(question)
            row.validation_report = report
            row.status = report.resulting_status()
            evaluation = (
                self._judge.evaluate(Question.model_validate(row))
                if report.passed
                else skipped_evaluation(question_id=row.id)
            )
            # Writes the history row and sets ``pedagogical_eval`` together, so
            # a generated evaluation is recorded the same way a re-run one is.
            record_evaluation(
                self._session,
                row.id,
                evaluation,
                run_id=run_id,
                trigger=EvaluationTrigger.GENERATION,
            )
            # Committed per section, not once at the end: a transport error on a
            # later section must not discard the questions already paid for
            # (ADR-032). The caller's rollback then only loses the section in
            # flight.
            self._session.commit()
            rows.append(row)
        return rows

    def _resolve_section_ids(
        self, source_section_ids: list[int] | None, book_id: int | None
    ) -> list[int]:
        if source_section_ids:
            return source_section_ids
        if book_id is not None:
            return [section.id for section in self._retrieval.sections_in_book(book_id)]
        raise InvalidQuestionSpecError(
            "Select at least one source section or a book.",
            detail="Question generation needs one or more source sections.",
        )

    @staticmethod
    def _row_from_question(question: Question) -> QuestionRow:
        """Copy every persisted domain question field into its ORM row."""
        return QuestionRow(
            curriculum_version_id=question.curriculum_version_id,
            topic_id=question.topic_id,
            subtopic_ids=question.subtopic_ids,
            kind=question.kind,
            question_type=question.question_type,
            difficulty=question.difficulty,
            status=question.status,
            prompt=question.prompt,
            reference_solution=question.reference_solution,
            tests=question.tests,
            spec=question.spec,
            content=question.content,
            validation_report=question.validation_report,
            generation_attempts=question.generation_attempts,
            pedagogical_eval=question.pedagogical_eval,
            original_prompt=question.original_prompt,
            original_reference_solution=question.original_reference_solution,
            original_tests=question.original_tests,
            generator_kind=question.generator_kind,
            generator_name=question.generator_name,
            generator_version=question.generator_version,
            regenerated_from_question_id=question.regenerated_from_question_id,
            regeneration_feedback=question.regeneration_feedback,
            priority=question.priority,
            times_used=question.times_used,
            personalization_context=question.personalization_context,
            created_at=question.created_at,
            updated_at=question.updated_at,
        )
