"""Section-first orchestration for base question generation and persistence."""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionType
from app.domain.questions import Question
from app.errors import InvalidQuestionSpecError
from app.evaluation import PedagogicalJudge, skipped_evaluation
from app.generation.base import BaseQuestionGenerator
from app.generation.spec import build_question_spec
from app.ingestion import SourceRetrieval
from app.llm import StructuredLLMClient
from app.persistence.models import QuestionRow
from app.persistence.repositories import CurriculumRepository, QuestionRepository
from app.personalization.embeddings import Embedder
from app.personalization.generator import PersonalizedContextGenerator


class GenerationService:
    """Validate a section set, generate one question per section, and store it."""

    def __init__(
        self,
        session: Session,
        *,
        client: StructuredLLMClient | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._session = session
        self._retrieval = SourceRetrieval(session)
        self._base = BaseQuestionGenerator(
            session=session, client=client, retrieval=self._retrieval
        )
        self._personalized = PersonalizedContextGenerator(
            session=session,
            client=client,
            retrieval=self._retrieval,
            embedder=embedder,
        )
        self._judge = PedagogicalJudge(session, client=client)
        self._curriculum = CurriculumRepository(session)
        self._questions = QuestionRepository(session)

    def generate_for_sections(
        self,
        *,
        curriculum_version_id: int,
        topic_id: int,
        subtopic_id: int,
        question_type: QuestionType,
        difficulty: Difficulty,
        source_section_ids: list[int] | None = None,
        book_id: int | None = None,
        seed: str | None = None,
        generator: Literal["base", "personalized"] = "base",
    ) -> list[QuestionRow]:
        """Generate and persist one question for each explicit or book section.

        All specs are validated before the first model call, preventing partial
        generation when a later selected id is invalid.
        """
        from app.validation import get_question_validator

        validator = get_question_validator(self._session)
        section_ids = self._resolve_section_ids(source_section_ids, book_id)
        specs = [
            build_question_spec(
                self._session,
                curriculum_version_id=curriculum_version_id,
                topic_id=topic_id,
                subtopic_ids=[subtopic_id],
                question_type=question_type,
                difficulty=difficulty,
                source_section_ids=[section_id],
                seed=seed,
            )
            for section_id in section_ids
        ]
        version = self._curriculum.get_with_tree(curriculum_version_id)
        topic = next(topic for topic in version.topics if topic.id == topic_id)
        subtopic_names = [
            subtopic.name for subtopic in topic.subtopics if subtopic.id == subtopic_id
        ]
        active = self._personalized if generator == "personalized" else self._base
        rows = []
        for spec in specs:
            row = self._questions.add(
                self._row_from_question(
                    active.generate_one(
                        spec,
                        topic_name=topic.name,
                        subtopic_names=subtopic_names,
                    )
                )
            )
            report = validator.validate(Question.model_validate(row))
            row.validation_report = report
            row.status = report.resulting_status()
            evaluation = (
                self._judge.evaluate(Question.model_validate(row))
                if report.passed
                else skipped_evaluation(question_id=row.id)
            )
            row.pedagogical_eval = evaluation.model_dump(mode="json")
            rows.append(row)
        self._session.commit()
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
            subtopic_id=question.subtopic_id,
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
            pedagogical_eval=question.pedagogical_eval,
            original_prompt=question.original_prompt,
            original_reference_solution=question.original_reference_solution,
            original_tests=question.original_tests,
            generator_kind=question.generator_kind,
            generator_name=question.generator_name,
            generator_version=question.generator_version,
            priority=question.priority,
            times_used=question.times_used,
            personalization_context=question.personalization_context,
            created_at=question.created_at,
            updated_at=question.updated_at,
        )
