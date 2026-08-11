"""Repositories: the only way other subsystems reach the database.

Each repository takes a :class:`~sqlalchemy.orm.Session` and exposes the small
set of operations needed today (count / list / add / get). Query logic belongs
here rather than in routes or services.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domain.enums import BookStatus, CurriculumStatus
from app.errors import NotFoundError
from app.persistence.models import (
    BookChapterRow,
    BookRow,
    BookSectionRow,
    CurriculumVersionRow,
    PreferenceStatementRow,
    ProfessorReviewRow,
    QuestionRow,
    ReviewEmbeddingRow,
    SubtopicEvidenceRow,
    SubtopicRow,
    TopicRow,
)


class BookRepository:
    """Uploaded textbooks."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(BookRow)) or 0

    def list_recent(self, limit: int = 50) -> list[BookRow]:
        stmt = select(BookRow).order_by(BookRow.created_at.desc(), BookRow.id.desc()).limit(limit)
        return list(self._session.scalars(stmt))

    def list_usable(self) -> list[BookRow]:
        """Books whose text may ground curriculum work.

        Every stored book validated on import, so this is all of them; the filter
        is explicit so a future status cannot silently become groundable.
        """
        stmt = (
            select(BookRow)
            .where(BookRow.status.in_((BookStatus.IMPORTED, BookStatus.PARTIAL)))
            .order_by(BookRow.created_at.desc(), BookRow.id.desc())
        )
        return list(self._session.scalars(stmt))

    def get(self, book_id: int) -> BookRow:
        row = self._session.get(BookRow, book_id)
        if row is None:
            raise NotFoundError(f"Book {book_id} does not exist.")
        return row

    def get_with_structure(self, book_id: int) -> BookRow:
        """Load a book with its chapters and their sections eagerly.

        Section ``text`` is included: it is what the professor came to read, and
        loading it lazily per section would mean one query per section.
        """
        stmt = (
            select(BookRow)
            .options(selectinload(BookRow.chapters).selectinload(BookChapterRow.sections))
            .where(BookRow.id == book_id)
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError(f"Book {book_id} does not exist.")
        return row

    def add(self, book: BookRow) -> BookRow:
        self._session.add(book)
        self._session.flush()
        return book


class BookStructureRepository:
    """Extracted chapters and sections.

    This is the retrieval surface later question generation uses to fetch and
    cite grounding text, so every read here can be traced back to a book,
    chapter, section and page range.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def section_count(self, book_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(BookSectionRow)
        if book_id is not None:
            stmt = stmt.where(BookSectionRow.book_id == book_id)
        return self._session.scalar(stmt) or 0

    def get_section(self, section_id: int) -> BookSectionRow:
        """One section, with its chapter and book loaded for citation."""
        stmt = (
            select(BookSectionRow)
            .options(
                joinedload(BookSectionRow.chapter),
                joinedload(BookSectionRow.book),
            )
            .where(BookSectionRow.id == section_id)
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError(f"Section {section_id} does not exist.")
        return row

    def sections_in_chapter(self, chapter_id: int) -> list[BookSectionRow]:
        stmt = (
            select(BookSectionRow)
            .where(BookSectionRow.chapter_id == chapter_id)
            .order_by(BookSectionRow.position, BookSectionRow.id)
        )
        return list(self._session.scalars(stmt))

    def sections_in_book(self, book_id: int) -> list[BookSectionRow]:
        stmt = (
            select(BookSectionRow)
            .where(BookSectionRow.book_id == book_id)
            .order_by(BookSectionRow.position, BookSectionRow.id)
        )
        return list(self._session.scalars(stmt))

    def chapters_in_book(self, book_id: int) -> list[BookChapterRow]:
        stmt = (
            select(BookChapterRow)
            .options(selectinload(BookChapterRow.sections))
            .where(BookChapterRow.book_id == book_id)
            .order_by(BookChapterRow.position, BookChapterRow.id)
        )
        return list(self._session.scalars(stmt))

    def get_chapter(self, chapter_id: int) -> BookChapterRow:
        row = self._session.get(BookChapterRow, chapter_id)
        if row is None:
            raise NotFoundError(f"Chapter {chapter_id} does not exist.")
        return row

    def replace_structure(
        self, book: BookRow, chapters: list[BookChapterRow], sections: list[BookSectionRow]
    ) -> None:
        """Attach a freshly extracted structure to ``book``, discarding any prior one.

        Re-extraction is expected to be idempotent from the professor's point of
        view, so this replaces rather than appends.
        """
        book.chapters.clear()
        book.sections.clear()
        self._session.flush()
        book.chapters.extend(chapters)
        book.sections.extend(sections)
        self._session.flush()


class CurriculumRepository:
    """Curriculum versions and their Topic -> Subtopic trees."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(CurriculumVersionRow)) or 0

    def list_versions(self, limit: int = 50) -> list[CurriculumVersionRow]:
        stmt = (
            select(CurriculumVersionRow)
            .options(selectinload(CurriculumVersionRow.topics))
            .order_by(CurriculumVersionRow.created_at.desc(), CurriculumVersionRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def get_approved(self) -> CurriculumVersionRow | None:
        """Return the most recently approved version, if any.

        Question generation must ground itself in an approved version; callers
        treat ``None`` as "curriculum not approved yet".
        """
        stmt = (
            select(CurriculumVersionRow)
            .where(CurriculumVersionRow.status == CurriculumStatus.APPROVED)
            .order_by(CurriculumVersionRow.approved_at.desc(), CurriculumVersionRow.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def get_latest(self) -> CurriculumVersionRow | None:
        """The most recently created version, approved or not.

        What the Curriculum page shows by default: the professor's last proposal
        is what they came back to review.
        """
        stmt = (
            select(CurriculumVersionRow)
            .order_by(CurriculumVersionRow.created_at.desc(), CurriculumVersionRow.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def get_with_tree(self, version_id: int) -> CurriculumVersionRow:
        """One version with its topics, subtopics and evidence loaded eagerly.

        Evidence is included because the hierarchy view shows per-subtopic
        section and book counts; loading it lazily would be one query per
        subtopic.

        Raises:
            NotFoundError: if no such version exists.
        """
        stmt = (
            select(CurriculumVersionRow)
            .options(
                selectinload(CurriculumVersionRow.topics)
                .selectinload(TopicRow.subtopics)
                .selectinload(SubtopicRow.evidence)
            )
            .where(CurriculumVersionRow.id == version_id)
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError(f"Curriculum version {version_id} does not exist.")
        return row

    def get_subtopic(self, subtopic_id: int) -> SubtopicRow:
        """One subtopic with its evidence, and each evidence row's book and section.

        Raises:
            NotFoundError: if no such subtopic exists.
        """
        stmt = (
            select(SubtopicRow)
            .options(
                joinedload(SubtopicRow.topic),
                selectinload(SubtopicRow.evidence).joinedload(SubtopicEvidenceRow.book),
                selectinload(SubtopicRow.evidence).joinedload(SubtopicEvidenceRow.section),
            )
            .where(SubtopicRow.id == subtopic_id)
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError(f"Subtopic {subtopic_id} does not exist.")
        return row

    def subtopic_count(self, version_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(SubtopicRow)
            .join(TopicRow, SubtopicRow.topic_id == TopicRow.id)
            .where(TopicRow.curriculum_version_id == version_id)
        )
        return self._session.scalar(stmt) or 0

    def add(self, version: CurriculumVersionRow) -> CurriculumVersionRow:
        self._session.add(version)
        self._session.flush()
        return version


class QuestionRepository:
    """Generated questions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(QuestionRow)) or 0

    def count_by_status(self) -> dict[str, int]:
        stmt = select(QuestionRow.status, func.count()).group_by(QuestionRow.status)
        return {str(status): count for status, count in self._session.execute(stmt)}

    def list_recent(self, limit: int = 50) -> list[QuestionRow]:
        stmt = (
            select(QuestionRow)
            .order_by(QuestionRow.created_at.desc(), QuestionRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def get(self, question_id: int) -> QuestionRow:
        row = self._session.get(QuestionRow, question_id)
        if row is None:
            raise NotFoundError(f"Question {question_id} does not exist.")
        return row

    def add(self, question: QuestionRow) -> QuestionRow:
        self._session.add(question)
        self._session.flush()
        return question


class ProfessorReviewRepository:
    """Append-only professor feedback."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(ProfessorReviewRow)) or 0

    def list_recent(self, limit: int = 50) -> list[ProfessorReviewRow]:
        stmt = (
            select(ProfessorReviewRow)
            .order_by(ProfessorReviewRow.created_at.desc(), ProfessorReviewRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def add(self, review: ProfessorReviewRow) -> ProfessorReviewRow:
        self._session.add(review)
        self._session.flush()
        return review

    def count_by_decision(self) -> dict[str, int]:
        stmt = select(ProfessorReviewRow.decision, func.count()).group_by(
            ProfessorReviewRow.decision
        )
        return {str(decision): count for decision, count in self._session.execute(stmt)}

    def reason_counts(self) -> dict[str, int]:
        """Count structured reasons across all reviews (Python-side JSON parse)."""
        from app.domain.feedback import decode_reasons

        counts: dict[str, int] = {}
        rows = self._session.scalars(select(ProfessorReviewRow.reasons_json)).all()
        for raw in rows:
            for reason in decode_reasons(raw):
                key = reason.value
                counts[key] = counts.get(key, 0) + 1
        return counts

    def list_with_questions(self, limit: int = 50) -> list[ProfessorReviewRow]:
        stmt = (
            select(ProfessorReviewRow)
            .options(joinedload(ProfessorReviewRow.question))
            .order_by(ProfessorReviewRow.created_at.desc(), ProfessorReviewRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).unique())


class PreferenceRepository:
    """Professor preference statements inferred from review history."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, row: PreferenceStatementRow) -> PreferenceStatementRow:
        self._session.add(row)
        self._session.flush()
        return row

    def get(self, preference_id: int) -> PreferenceStatementRow:
        row = self._session.get(PreferenceStatementRow, preference_id)
        if row is None:
            raise NotFoundError(f"Preference {preference_id} does not exist.")
        return row

    def list_all(self, *, active_only: bool = False) -> list[PreferenceStatementRow]:
        stmt = select(PreferenceStatementRow).order_by(
            PreferenceStatementRow.confidence.desc(),
            PreferenceStatementRow.id.desc(),
        )
        if active_only:
            stmt = stmt.where(PreferenceStatementRow.active.is_(True))
        return list(self._session.scalars(stmt))

    def list_for_generation(self, *, soft_floor: float) -> list[PreferenceStatementRow]:
        stmt = (
            select(PreferenceStatementRow)
            .where(
                PreferenceStatementRow.active.is_(True),
                PreferenceStatementRow.confidence >= soft_floor,
            )
            .order_by(
                PreferenceStatementRow.confidence.desc(),
                PreferenceStatementRow.id.desc(),
            )
        )
        return list(self._session.scalars(stmt))


class ReviewEmbeddingRepository:
    """Cached embedding vectors for professor reviews."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_review(self, review_id: int) -> ReviewEmbeddingRow | None:
        stmt = select(ReviewEmbeddingRow).where(ReviewEmbeddingRow.review_id == review_id)
        return self._session.scalars(stmt).first()

    def upsert(self, row: ReviewEmbeddingRow) -> ReviewEmbeddingRow:
        existing = self.get_for_review(row.review_id)
        if existing is None:
            self._session.add(row)
            self._session.flush()
            return row
        existing.model_id = row.model_id
        existing.vector_json = row.vector_json
        existing.content_hash = row.content_hash
        self._session.flush()
        return existing
