"""Section-first orchestration for question generation and persistence.

One generator, not two. Personalization is the per-type instruction the
generator already reads (ADR-033), so there is no longer a "personalized"
variant to choose between: every question is generated with whatever has been
learned for its type.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, EvaluationTrigger, JudgeMetricId, QuestionType
from app.domain.questions import Question
from app.errors import InvalidQuestionSpecError
from app.evaluation import (
    PedagogicalEvaluation,
    PedagogicalJudge,
    new_run_id,
    record_evaluation,
    skipped_evaluation,
)
from app.evaluation.custom import CustomRule
from app.evaluation.schema import MetricStatus
from app.generation.base import BaseQuestionGenerator
from app.generation.batch import ChunkQuestionRequest, compile_chunk_requests
from app.generation.prompts import RoundExamples
from app.generation.review import DuplicateCheck, RoundReview
from app.generation.spec import QuestionSpec, build_question_spec, require_approved_version
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient
from app.persistence.models import CurriculumVersionRow, QuestionRow, QuestionSimilarityRow
from app.persistence.repositories import QuestionRepository, _source_section_ids


class GenerationService:
    """Validate a section set, generate one question per section, and store it."""

    def __init__(
        self,
        session: Session,
        *,
        client: StructuredLLMClient | None = None,
        snapshot_id: int | None = None,
        memory_as_of: datetime | None = None,
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
        self._client = client
        self._judge = PedagogicalJudge(
            session, client=client, snapshot_id=snapshot_id, memory_as_of=memory_as_of
        )
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
        run_id: str | None = None,
        on_question: Callable[[], None] | None = None,
        start_at: int = 0,
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

        ``run_id`` lets a caller that drives several ``generate_batch`` calls in
        one request -- the coverage "Generate" flow issues one per gap target so
        a provider failure isolates to that target -- keep every question under a
        single run id. Left ``None``, a fresh one is minted per call as before.

        ``on_question`` is called after each question commits, so a background job can
        count progress (``app.jobs``). ``start_at`` skips that many questions of the
        compiled plan -- the plan's order is fixed, so a retry of a run that stopped part-way
        generates exactly the questions it had not reached.
        """
        planned = compile_chunk_requests(chunks)[start_at:]
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
        return self._generate_specs(specs, version=version, run_id=run_id, on_question=on_question)

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
        run_id: str | None = None,
        on_question: Callable[[], None] | None = None,
    ) -> list[QuestionRow]:
        """Generate, validate, judge and persist one question per spec.

        One run id groups the questions generated by this call, so a generated
        evaluation is as attributable to a run as a re-run one is (ADR-030). A
        caller that spans several calls may pass its own ``run_id`` to keep them
        grouped; otherwise a fresh one is minted here.

        ``instructor_feedback`` is set only by :meth:`regenerate_from_question`
        and is forwarded verbatim to the generator; the section-first callers
        leave it ``None``.
        """
        run_id = run_id or new_run_id()
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
            if on_question is not None:
                on_question()
        return rows

    def generate_round_question(
        self,
        spec: QuestionSpec,
        *,
        version: CurriculumVersionRow,
        round_id: int | None,
        rules: Sequence[CustomRule] = (),
        examples: RoundExamples | None = None,
        run_id: str | None = None,
        duplicates: DuplicateCheck | None = None,
    ) -> QuestionRow | None:
        """Generate one round question, judged inside the retry loop; ``None`` when dropped.

        docs/QUESTION_SETUP_PLAN.md step 4: generate -> answer check -> difficulty judge ->
        topic judge -> custom rules. Any failure is fed back as a correction; after
        ``MAX_GENERATION_ATTEMPTS`` a question that still fails is **not stored**. A stored
        question carries ``style_id``, ``round_id`` and ``target_subtopic_id``, keeps the
        judge evaluation that passed it (no second judge run), and lands in the review queue.

        ``duplicates`` (ADR-063 point 6) runs before the judges: a duplicate is retried with
        "too similar to: ...", except on the last attempt, where it is judged as usual and, if
        kept, stored with a :class:`QuestionSimilarityRow` per resembled question -- as is any
        kept question that only resembles one. A kept duplicate always goes to the review
        queue, never auto-approved by trust routing.

        Flushes; the caller commits.

        A hard cell does this in two steps. First it generates a medium question and
        keeps it only when the answer check passes. Then it asks for a harder question
        made from that one, and the difficulty judge runs on the harder question.
        """
        if not spec.is_round_spec:
            raise InvalidQuestionSpecError(
                "Round generation needs a target subtopic.",
                detail="Use generate_for_sections for section-only specs.",
            )
        review = RoundReview(
            self._judge, rules, spec=spec, client=self._client, duplicates=duplicates
        )
        question = self._question_for_round(spec, version=version, review=review, examples=examples)
        if not question.generation_attempts or not question.generation_attempts[-1].usable:
            self._maybe_store_audit(spec, review, round_id)
            return None
        evaluation = review.last_evaluation
        if evaluation is None:
            self._maybe_store_audit(spec, review, round_id)
            return None

        row = self._row_from_question(question)
        row.style_id = spec.style_id
        row.round_id = round_id
        row.target_subtopic_id = spec.target_subtopic_id
        row = self._questions.add(row)
        report = question.validation_report or self._validator.validate(question)
        row.validation_report = report
        row.status = report.resulting_status()
        evaluation = evaluation.model_copy(update={"question_id": row.id})
        stored = record_evaluation(
            self._session,
            row.id,
            evaluation,
            run_id=run_id or new_run_id(),
            trigger=EvaluationTrigger.GENERATION,
        )
        stored.custom_results = [result.model_dump(mode="json") for result in review.last_custom]
        for match in review.last_similar:
            self._session.add(
                QuestionSimilarityRow(
                    question_id=row.id,
                    similar_question_id=match.question_id,
                    score=match.score,
                    model=match.model,
                )
            )
        self._session.flush()
        from app.evaluation.trust import route_generated_question

        # A duplicate kept on the last attempt waits for the professor, who sees its flag.
        route_generated_question(
            self._session,
            row,
            review.last_custom,
            hold_for_review=any(match.duplicate for match in review.last_similar),
        )
        self._maybe_store_audit(spec, review, round_id)
        return row

    def _question_for_round(
        self,
        spec: QuestionSpec,
        *,
        version: CurriculumVersionRow,
        review: RoundReview,
        examples: RoundExamples | None,
    ) -> Question:
        """One round question. A hard cell is a valid medium question, then a harder one."""
        if spec.difficulty is not Difficulty.HARD:
            return self._generator.generate_one(
                spec, version=version, review=review, examples=examples
            )
        seed = self._generator.generate_one(
            spec.model_copy(update={"difficulty": Difficulty.MEDIUM}),
            version=version,
            examples=None,
        )
        if not seed.generation_attempts or not seed.generation_attempts[-1].usable:
            return seed
        return self._generator.generate_one(
            spec,
            version=version,
            review=review,
            examples=examples,
            follow_up=_harden_follow_up(seed),
        )

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

    def _maybe_store_audit(
        self,
        spec: QuestionSpec,
        review: RoundReview,
        round_id: int | None,
    ) -> None:
        """Keep at most two judge-failed drafts per round for the professor to confirm."""
        if round_id is None:
            return
        question = review.last_failed_question
        evaluation = review.last_failed_evaluation
        if question is None or evaluation is None:
            return
        metric = _audit_metric(evaluation)
        if metric is None:
            return
        if self._questions.count_audit_for_round(round_id) >= 2:
            return
        row = self._row_from_question(question)
        row.style_id = spec.style_id
        row.round_id = round_id
        row.target_subtopic_id = spec.target_subtopic_id
        row.audit = True
        row.audit_metric = metric
        row.audit_reason = _audit_reason(evaluation, metric)
        row = self._questions.add(row)
        report = question.validation_report or self._validator.validate(question)
        row.validation_report = report
        row.status = report.resulting_status()
        evaluation = evaluation.model_copy(update={"question_id": row.id})
        record_evaluation(
            self._session,
            row.id,
            evaluation,
            run_id=new_run_id(),
            trigger=EvaluationTrigger.GENERATION,
        )
        self._session.flush()


def _audit_metric(evaluation: PedagogicalEvaluation) -> str | None:
    """Which completed judge failed first; skip ERROR / skipped panels."""
    difficulty = evaluation.metric(JudgeMetricId.DIFFICULTY)
    if (
        difficulty is not None
        and difficulty.status is MetricStatus.COMPLETED
        and difficulty.passed is False
    ):
        return "difficulty"
    topic = evaluation.metric(JudgeMetricId.SUBTOPIC)
    if topic is not None and topic.status is MetricStatus.COMPLETED and topic.passed is False:
        return "topic"
    return None


def _audit_reason(evaluation: PedagogicalEvaluation, metric: str) -> str:
    key = JudgeMetricId.DIFFICULTY if metric == "difficulty" else JudgeMetricId.SUBTOPIC
    result = evaluation.metric(key)
    return (result.rationale or "").strip() if result is not None else ""


def _harden_follow_up(seed: Question) -> str:
    """Tell the model to make a passing question harder without breaking the answer check."""
    content = seed.content if isinstance(seed.content, dict) else {}
    code = content.get("code")
    lines = [
        "This question already passes the answer check. Make a harder question from it.",
        "Keep the same subtopic and the same question type.",
        "The harder question must still pass the answer check.",
        "",
        f"Prompt:\n{seed.prompt}",
    ]
    if isinstance(code, str) and code.strip():
        lines.append(f"Code:\n{code}")
    solution = seed.reference_solution
    if isinstance(solution, str) and solution.strip() and solution != code:
        lines.append(f"Reference solution:\n{solution}")
    return "\n".join(lines)
