"""Repositories: the only way other subsystems reach the database.

Each repository takes a :class:`~sqlalchemy.orm.Session` and exposes the small
set of operations needed today (count / list / add / get). Query logic belongs
here rather than in routes or services.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domain.enums import (
    BookStatus,
    CurriculumStatus,
    Difficulty,
    JudgeMetricId,
    QuadrantCell,
    QuestionStatus,
    QuestionType,
)
from app.domain.mastery import DEFAULT_BKT_PARAMETERS, INITIAL_SUBTOPIC_WEAKNESS
from app.errors import NotFoundError
from app.persistence.models import (
    BookChapterRow,
    BookRow,
    BookSectionRow,
    CurriculumVersionRow,
    JudgeBatchRunRow,
    JudgePromptRow,
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    QuestionSetMemberRow,
    QuestionSetVersionRow,
    QuestionSubtopicRow,
    ReviewOutcomeRow,
    StudentAttemptRow,
    StudentRow,
    StudentSubtopicWeaknessRow,
    StudentTopicMasteryRow,
    SubtopicEvidenceRow,
    SubtopicRow,
    TopicRow,
    TrainingSessionRow,
    TypeInstructionRow,
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

    def delete(self, book: BookRow) -> None:
        """Remove a book and, by cascade, its chapters and sections.

        Questions are not touched: they hold their grounding as data rather than
        as a foreign key, so the caller is responsible for warning about the
        citations this strands. See :class:`app.ingestion.service.BookImportService`.
        """
        self._session.delete(book)
        self._session.flush()

    def section_ids(self, book_id: int) -> list[int]:
        """Every section id belonging to one book, for reference counting."""
        stmt = select(BookSectionRow.id).where(BookSectionRow.book_id == book_id)
        return list(self._session.scalars(stmt))


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

    def topic_ids_for(self, subtopic_ids: Collection[int]) -> dict[int, int]:
        """Map each subtopic id to the id of the topic that owns it.

        A light lookup on purpose. :meth:`get_subtopic` eagerly loads evidence,
        books and sections for the display page; the adaptive engine needs one
        integer per draw and must not pay for that.
        """
        ids = list(subtopic_ids)
        if not ids:
            return {}
        stmt = select(SubtopicRow.id, SubtopicRow.topic_id).where(SubtopicRow.id.in_(ids))
        return dict(self._session.execute(stmt).all())

    def topic_names_for(self, topic_ids: Collection[int]) -> dict[int, str]:
        """Display name per topic id, for ids that still exist."""
        ids = list(topic_ids)
        if not ids:
            return {}
        stmt = select(TopicRow.id, TopicRow.name).where(TopicRow.id.in_(ids))
        return dict(self._session.execute(stmt).all())

    def subtopic_labels_for(self, subtopic_ids: Collection[int]) -> dict[int, tuple[str, str]]:
        """``(subtopic name, owning topic name)`` per subtopic id.

        One query rather than :meth:`get_subtopic` per row: a progress page names
        every subtopic a student has been measured on, and that page must not
        cost one round trip each.
        """
        ids = list(subtopic_ids)
        if not ids:
            return {}
        stmt = (
            select(SubtopicRow.id, SubtopicRow.name, TopicRow.name)
            .join(TopicRow, TopicRow.id == SubtopicRow.topic_id)
            .where(SubtopicRow.id.in_(ids))
        )
        return {
            subtopic_id: (subtopic_name, topic_name)
            for subtopic_id, subtopic_name, topic_name in self._session.execute(stmt)
        }

    def subtopic_count(self, version_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(SubtopicRow)
            .join(TopicRow, SubtopicRow.topic_id == TopicRow.id)
            .where(TopicRow.curriculum_version_id == version_id)
        )
        return self._session.scalar(stmt) or 0

    def subtopic_counts_for(self, version_ids: Collection[int]) -> dict[int, int]:
        """Subtopics per curriculum version, for a list that must not cost a query per row.

        A version whose topics hold no subtopics produces no group row, so callers
        default to zero. An upload cannot produce one -- ``subtopics`` declares
        ``min_length=1`` -- but a legacy proposal row can.
        """
        ids = list(version_ids)
        if not ids:
            return {}
        stmt = (
            select(TopicRow.curriculum_version_id, func.count(SubtopicRow.id))
            .join(SubtopicRow, SubtopicRow.topic_id == TopicRow.id)
            .where(TopicRow.curriculum_version_id.in_(ids))
            .group_by(TopicRow.curriculum_version_id)
        )
        return dict(self._session.execute(stmt).all())

    def get_version(self, version_id: int) -> CurriculumVersionRow:
        """One version without its tree, for an edit or a delete.

        Raises:
            NotFoundError: if no such version exists.
        """
        row = self._session.get(CurriculumVersionRow, version_id)
        if row is None:
            raise NotFoundError(f"Curriculum version {version_id} does not exist.")
        return row

    def activate(self, version: CurriculumVersionRow) -> CurriculumVersionRow:
        """Make this version the one ``get_approved()`` returns.

        Activation is an ordering change, not a structural edit: the row stays
        approved and simply becomes the most recently approved one.
        """
        version.approved_at = datetime.now(UTC)
        self._session.flush()
        return version

    def get_topic(self, topic_id: int) -> TopicRow:
        """One topic with its subtopics, which is what a rename has to return.

        Raises:
            NotFoundError: if no such topic exists.
        """
        stmt = (
            select(TopicRow)
            .options(selectinload(TopicRow.subtopics))
            .where(TopicRow.id == topic_id)
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError(f"Topic {topic_id} does not exist.")
        return row

    def sibling_topic_names(self, version_id: int, *, exclude_topic_id: int) -> list[str]:
        """The names a topic in this version may not collide with once renamed."""
        stmt = select(TopicRow.name).where(
            TopicRow.curriculum_version_id == version_id, TopicRow.id != exclude_topic_id
        )
        return list(self._session.scalars(stmt))

    def sibling_subtopic_names(self, topic_id: int, *, exclude_subtopic_id: int) -> list[str]:
        """The names a subtopic under this topic may not collide with once renamed."""
        stmt = select(SubtopicRow.name).where(
            SubtopicRow.topic_id == topic_id, SubtopicRow.id != exclude_subtopic_id
        )
        return list(self._session.scalars(stmt))

    def topic_ids_in(self, version_id: int) -> list[int]:
        """Every topic id belonging to a version, for counting what cites it."""
        stmt = select(TopicRow.id).where(TopicRow.curriculum_version_id == version_id)
        return list(self._session.scalars(stmt))

    def subtopic_ids_in(self, version_id: int) -> list[int]:
        """Every subtopic id belonging to a version, for counting what cites it."""
        stmt = (
            select(SubtopicRow.id)
            .join(TopicRow, SubtopicRow.topic_id == TopicRow.id)
            .where(TopicRow.curriculum_version_id == version_id)
        )
        return list(self._session.scalars(stmt))

    def topics_with_subtopics_in_order(
        self, curriculum_version_id: int
    ) -> list[tuple[int, list[int]]]:
        """Every topic in this version, position-ordered, with its subtopic ids.

        Powers sequential topic progression in the adaptive engine: it walks
        this list in order rather than pooling every topic's subtopics
        together. A topic with no subtopics still appears, with an empty list,
        so the engine can skip it rather than stall.
        """
        stmt = (
            select(TopicRow.id, SubtopicRow.id)
            .outerjoin(SubtopicRow, SubtopicRow.topic_id == TopicRow.id)
            .where(TopicRow.curriculum_version_id == curriculum_version_id)
            .order_by(TopicRow.position, TopicRow.id, SubtopicRow.position, SubtopicRow.id)
        )
        ordered: dict[int, list[int]] = {}
        for topic_id, subtopic_id in self._session.execute(stmt).all():
            ordered.setdefault(topic_id, [])
            if subtopic_id is not None:
                ordered[topic_id].append(subtopic_id)
        return list(ordered.items())

    def delete(self, version: CurriculumVersionRow) -> None:
        """Remove a version, and with it its topics, subtopics and evidence.

        Only those four tables go. Questions, question sets and student state hold
        plain integer references that the ORM cannot see and SQLite does not
        enforce, so they are left pointing at rows that no longer exist -- counted
        and reported by :class:`app.curriculum.library.CurriculumLibraryService`
        before the caller decides, never silently repaired here.
        """
        self._session.delete(version)
        self._session.flush()

    def add(self, version: CurriculumVersionRow) -> CurriculumVersionRow:
        self._session.add(version)
        self._session.flush()
        return version


#: Statuses the review queue never offers (ADR-032). A question that failed
#: deterministic validation has already been ruled on by a check that names the
#: fault exactly, so there is no verdict left for a professor to add -- and
#: professor attention is the scarcest resource in this system. Such questions
#: stay in the bank, where the generator's failure modes are meant to be read.
NOT_REVIEWABLE_STATUSES = (QuestionStatus.VALIDATION_FAILED,)


def _spec_sections(spec: object) -> set[int]:
    """The section ids a stored ``QuestionSpec`` names, tolerating older rows."""
    if not isinstance(spec, dict):
        return set()
    section_ids = spec.get("source_section_ids")
    if not isinstance(section_ids, list):
        return set()
    return {item for item in section_ids if isinstance(item, int)}


class QuestionRepository:
    """Generated questions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(QuestionRow)) or 0

    def count_by_status(self) -> dict[str, int]:
        stmt = select(QuestionRow.status, func.count()).group_by(QuestionRow.status)
        return {str(status): count for status, count in self._session.execute(stmt)}

    def count_reviewable(self) -> int:
        """Questions a professor could be asked to rule on.

        Excludes the same statuses :meth:`list_unreviewed` excludes, so the review
        queue's "reviewed of total" can actually reach completion. Counting the
        whole bank there would leave a permanent remainder of questions the queue
        will never offer.
        """
        stmt = (
            select(func.count())
            .select_from(QuestionRow)
            .where(QuestionRow.status.not_in(NOT_REVIEWABLE_STATUSES))
        )
        return self._session.scalar(stmt) or 0

    def count_grounded_in_sections(self, section_ids: Collection[int]) -> int:
        """How many questions were generated from any of these sections.

        A question records its grounding inside the frozen ``QuestionSpec`` it was
        generated from, not as a foreign key, so this reads specs rather than
        joining. Deleting those sections therefore would not delete the questions:
        it would leave their citation pointing at nothing, which is exactly what
        the caller needs to warn about before it happens.
        """
        wanted = set(section_ids)
        if not wanted:
            return 0
        stmt = select(QuestionRow.spec).where(QuestionRow.spec.is_not(None))
        return sum(1 for spec in self._session.scalars(stmt) if wanted & _spec_sections(spec))

    def count_for_curriculum_version(self, version_id: int) -> int:
        """Questions whose grounding names this curriculum version.

        A plain column read, unlike :meth:`count_grounded_in_sections`: a
        question's curriculum version *is* a column, even though nothing enforces
        it. Deleting the version leaves this integer pointing at nothing.
        """
        stmt = (
            select(func.count())
            .select_from(QuestionRow)
            .where(QuestionRow.curriculum_version_id == version_id)
        )
        return self._session.scalar(stmt) or 0

    def count_subtopic_links(self, subtopic_ids: Collection[int]) -> int:
        """Question-to-subtopic taggings that name any of these subtopics.

        This is what coverage counts and what adaptive selection draws from, so a
        tagging left pointing at a deleted subtopic removes its question from both
        without marking it as anything.
        """
        ids = list(subtopic_ids)
        if not ids:
            return 0
        stmt = (
            select(func.count())
            .select_from(QuestionSubtopicRow)
            .where(QuestionSubtopicRow.subtopic_id.in_(ids))
        )
        return self._session.scalar(stmt) or 0

    def list_recent(
        self,
        limit: int = 50,
        *,
        statuses: Collection[QuestionStatus] | None = None,
        curriculum_version_id: int | None = None,
        section_id: int | None = None,
    ) -> list[QuestionRow]:
        """The newest questions, optionally narrowed to particular statuses.

        ``statuses`` is a filter, never a default: both callers decide for
        themselves what to show, and an empty collection means "nothing matches"
        rather than "no filter". ``curriculum_version_id`` narrows the same way,
        so a taxonomy filter applies to the whole bank rather than only to
        whatever page ``limit`` happened to load.

        ``section_id`` narrows to questions grounded in that one section. Like
        :meth:`count_grounded_in_sections`, this reads the frozen spec rather than
        a foreign key, so it is applied by scanning candidates in Python after the
        other filters and before ``limit`` is taken -- a section rarely produces
        more than a handful of questions, so this stays cheap in practice.
        """
        stmt = select(QuestionRow).order_by(QuestionRow.created_at.desc(), QuestionRow.id.desc())
        if statuses is not None:
            stmt = stmt.where(QuestionRow.status.in_(list(statuses)))
        if curriculum_version_id is not None:
            stmt = stmt.where(QuestionRow.curriculum_version_id == curriculum_version_id)
        if section_id is not None:
            rows = []
            for row in self._session.scalars(stmt):
                if section_id not in _spec_sections(row.spec):
                    continue
                rows.append(row)
                if len(rows) >= limit:
                    break
            return rows
        return list(self._session.scalars(stmt.limit(limit)))

    def count_by_curriculum_version(self) -> dict[str, int]:
        """How many questions each curriculum version grounds, whole bank.

        A question generated before this column existed has no version to name;
        those are counted under ``"none"`` rather than dropped.
        """
        stmt = select(QuestionRow.curriculum_version_id, func.count()).group_by(
            QuestionRow.curriculum_version_id
        )
        return {
            (str(version_id) if version_id is not None else "none"): count
            for version_id, count in self._session.execute(stmt)
        }

    def get(self, question_id: int) -> QuestionRow:
        row = self._session.get(QuestionRow, question_id)
        if row is None:
            raise NotFoundError(f"Question {question_id} does not exist.")
        return row

    def list_reviewed_with_evaluation(self) -> list[QuestionRow]:
        """Questions carrying both a stored judge evaluation and a review.

        The reviews are eager-loaded in one further query, because calibration
        reads every review of every matching question and would otherwise issue
        one query per question. Unbounded on purpose: a sample restricted to the
        newest questions would report a rate for a slice while naming it the
        judge's accuracy.
        """
        stmt = (
            select(QuestionRow)
            .where(QuestionRow.pedagogical_eval.is_not(None), QuestionRow.reviews.any())
            .options(selectinload(QuestionRow.reviews))
            .order_by(QuestionRow.id)
        )
        return list(self._session.scalars(stmt))

    def count_reviewed(self) -> int:
        """How many reviewable questions carry at least one professor verdict.

        Restricted to the same set as :meth:`count_reviewable` so the two can be
        subtracted. A question that was reviewed before ADR-032 excluded its
        status would otherwise be counted as progress against a total it is no
        longer part of, and the remainder could go negative.
        """
        stmt = (
            select(func.count())
            .select_from(QuestionRow)
            .where(
                QuestionRow.reviews.any(),
                QuestionRow.status.not_in(NOT_REVIEWABLE_STATUSES),
            )
        )
        return self._session.scalar(stmt) or 0

    def list_unreviewed(
        self, *, after_id: int | None = None, require_evaluation: bool = False
    ) -> list[QuestionRow]:
        """Questions no professor has ruled on yet, lowest id first.

        ``after_id`` is the review queue's cursor: it is how skipping a question
        moves past it without a stored position. Ordering by id rather than by
        recency keeps that cursor monotonic, so a pass over the bank cannot
        revisit a question it already offered.

        ``require_evaluation`` narrows to questions carrying a stored judge
        evaluation. Whether that evaluation actually *completed* lives inside the
        JSON column and is the caller's to decide: that vocabulary belongs to
        :mod:`app.evaluation`, which persistence must not import (ADR-026).

        :data:`NOT_REVIEWABLE_STATUSES` is excluded unconditionally, in every
        mode: a question that failed deterministic validation is not awaiting a
        verdict, it already has one.
        """
        stmt = (
            select(QuestionRow)
            .where(
                ~QuestionRow.reviews.any(),
                QuestionRow.status.not_in(NOT_REVIEWABLE_STATUSES),
            )
            .order_by(QuestionRow.id)
        )
        if after_id is not None:
            stmt = stmt.where(QuestionRow.id > after_id)
        if require_evaluation:
            stmt = stmt.where(QuestionRow.pedagogical_eval.is_not(None))
        return list(self._session.scalars(stmt))

    def list_judgeable(self) -> list[QuestionRow]:
        """Questions the pedagogical judge is allowed to score.

        The judge never runs on a question that failed or skipped deterministic
        validation (ADR-024), so a bulk re-run must exclude them rather than
        re-deciding that rule for itself. ``passed`` lives inside a JSON column,
        so the SQL narrows to questions that have a report at all and the flag
        is read from the decoded model.
        """
        stmt = (
            select(QuestionRow)
            .where(QuestionRow.validation_report.is_not(None))
            .order_by(QuestionRow.id)
        )
        return [
            row
            for row in self._session.scalars(stmt)
            if row.validation_report is not None and row.validation_report.passed
        ]

    def list_evaluated_without_history(self) -> list[QuestionRow]:
        """Questions carrying a current evaluation that no history row records.

        The backfill set (ADR-030): evaluations written before this table
        existed. Empty once a backfill pass has run, which is what makes the
        pass idempotent without a marker row.
        """
        recorded = select(QuestionEvaluationRow.question_id).distinct()
        stmt = (
            select(QuestionRow)
            .where(
                QuestionRow.pedagogical_eval.is_not(None),
                QuestionRow.id.not_in(recorded),
            )
            .order_by(QuestionRow.id)
        )
        return list(self._session.scalars(stmt))

    def count_by_source_section(self) -> dict[int, int]:
        """How many questions each source section has already produced.

        Read in Python rather than in SQL because the section ids live inside a
        JSON column, and SQLite's JSON support is not worth depending on for a
        count this small. The frozen spec is authoritative; ``content`` is the
        fallback for a row stored before a spec was persisted, so an early
        question still reports against the section it actually came from.
        """
        counts: dict[int, int] = {}
        for row in self._session.scalars(select(QuestionRow)):
            for section_id in _source_section_ids(row):
                counts[section_id] = counts.get(section_id, 0) + 1
        return counts

    def add(self, question: QuestionRow) -> QuestionRow:
        self._session.add(question)
        self._session.flush()
        return question


def _source_section_ids(row: QuestionRow) -> list[int]:
    """The section ids one question was generated from, or an empty list."""
    spec = row.spec or {}
    ids = spec.get("source_section_ids")
    if isinstance(ids, list):
        return [section_id for section_id in ids if isinstance(section_id, int)]
    sources = (row.content or {}).get("sources")
    if not isinstance(sources, list):
        return []
    return [
        source["section_id"]
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("section_id"), int)
    ]


class QuestionEvaluationRepository:
    """Append-only pedagogical evaluation history (ADR-030).

    There is no update or delete here on purpose: an evaluation records what the
    judge said at a moment, and a later run disagreeing with it is a second row,
    never an edit of the first.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, row: QuestionEvaluationRow) -> QuestionEvaluationRow:
        self._session.add(row)
        self._session.flush()
        return row

    def list_for_question(self, question_id: int) -> list[QuestionEvaluationRow]:
        """Every evaluation of one question, newest first."""
        stmt = (
            select(QuestionEvaluationRow)
            .where(QuestionEvaluationRow.question_id == question_id)
            .order_by(
                QuestionEvaluationRow.created_at.desc(),
                QuestionEvaluationRow.id.desc(),
            )
        )
        return list(self._session.scalars(stmt))

    def get_for_run(self, run_id: str, question_id: int) -> QuestionEvaluationRow | None:
        """The row a given run already wrote for a question, if any.

        Consulted before ingesting a result so that re-polling a completed run
        adds nothing rather than raising on the unique constraint.
        """
        stmt = select(QuestionEvaluationRow).where(
            QuestionEvaluationRow.run_id == run_id,
            QuestionEvaluationRow.question_id == question_id,
        )
        return self._session.scalars(stmt).first()

    def question_ids_for_run(self, run_id: str) -> set[int]:
        stmt = select(QuestionEvaluationRow.question_id).where(
            QuestionEvaluationRow.run_id == run_id
        )
        return set(self._session.scalars(stmt))

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(QuestionEvaluationRow)) or 0


class JudgeBatchRunRepository:
    """Bulk judge re-runs and their provider job ids (ADR-030)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, row: JudgeBatchRunRow) -> JudgeBatchRunRow:
        self._session.add(row)
        self._session.flush()
        return row

    def get(self, run_id: str) -> JudgeBatchRunRow:
        stmt = select(JudgeBatchRunRow).where(JudgeBatchRunRow.run_id == run_id)
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError(f"Judge batch run {run_id!r} does not exist.")
        return row

    def find(self, run_id: str) -> JudgeBatchRunRow | None:
        stmt = select(JudgeBatchRunRow).where(JudgeBatchRunRow.run_id == run_id)
        return self._session.scalars(stmt).first()

    def list_recent(self, limit: int = 20) -> list[JudgeBatchRunRow]:
        stmt = (
            select(JudgeBatchRunRow)
            .order_by(JudgeBatchRunRow.created_at.desc(), JudgeBatchRunRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))


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
        """Count structured reasons across all reviews, decoded column-side."""
        reasons = self._session.scalars(select(ProfessorReviewRow.reasons)).all()
        return Counter(reason.value for row in reasons for reason in row)

    def list_with_questions(self, limit: int = 50) -> list[ProfessorReviewRow]:
        stmt = (
            select(ProfessorReviewRow)
            .options(joinedload(ProfessorReviewRow.question))
            .order_by(ProfessorReviewRow.created_at.desc(), ProfessorReviewRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).unique())


class ReviewOutcomeRepository:
    """The dataset written when a review lands (ADR-037).

    Append-only, like the reviews it describes. There is no update method: an
    outcome states what the judge and the professor said at one moment, and a
    row that could be rewritten would not answer that.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, outcome: ReviewOutcomeRow) -> ReviewOutcomeRow:
        self._session.add(outcome)
        self._session.flush()
        return outcome

    def get_for_review(self, review_id: int) -> ReviewOutcomeRow | None:
        stmt = select(ReviewOutcomeRow).where(ReviewOutcomeRow.review_id == review_id)
        return self._session.scalars(stmt).first()

    def list_recent(self, limit: int = 50) -> list[ReviewOutcomeRow]:
        stmt = (
            select(ReviewOutcomeRow)
            .order_by(ReviewOutcomeRow.created_at.desc(), ReviewOutcomeRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def list_in_cells(
        self,
        cells: Collection[QuadrantCell],
        *,
        question_type: QuestionType | None = None,
        include_held_out: bool = True,
        limit: int = 500,
    ) -> list[ReviewOutcomeRow]:
        """The dataset rows in the given cells, newest first.

        ``include_held_out`` is false when the caller is about to *repair* a
        judge: reading the held-back third while rewriting a prompt turns the
        check set into a second tuning set (ADR-035).
        """
        stmt = select(ReviewOutcomeRow).where(ReviewOutcomeRow.cell.in_(list(cells)))
        if question_type is not None:
            stmt = stmt.where(ReviewOutcomeRow.question_type == question_type)
        if not include_held_out:
            stmt = stmt.where(ReviewOutcomeRow.held_out.is_(False))
        stmt = stmt.order_by(ReviewOutcomeRow.created_at.desc(), ReviewOutcomeRow.id.desc())
        return list(self._session.scalars(stmt.limit(limit)))

    def list_disagreements_for(
        self, metric: JudgeMetricId, *, include_held_out: bool = False, limit: int = 60
    ) -> list[ReviewOutcomeRow]:
        """Rows where this judge was the one at fault, newest first (ADR-039).

        Held-out rows are excluded by default because the caller is normally
        about to repair the judge, and reading the reserved third while
        rewriting its prompt turns the check set into a second tuning set
        (ADR-035). This is the one query where that default matters most, so it
        is the default rather than a flag the caller must remember.

        The review and the question travel with each row: a rewriter needs the
        question that was misjudged and the professor's reasons, and loading
        them lazily would mean two queries per disagreement.
        """
        stmt = (
            select(ReviewOutcomeRow)
            .options(
                joinedload(ReviewOutcomeRow.review),
                joinedload(ReviewOutcomeRow.question),
            )
            .where(
                ReviewOutcomeRow.cell.in_([QuadrantCell.MISSED, QuadrantCell.FALSE_ALARM]),
            )
        )
        if not include_held_out:
            stmt = stmt.where(ReviewOutcomeRow.held_out.is_(False))
        stmt = stmt.order_by(ReviewOutcomeRow.created_at.desc(), ReviewOutcomeRow.id.desc())
        rows = list(self._session.scalars(stmt).unique())
        # Filtered in Python: ``attributed_metrics`` is a JSON list, and matching
        # inside it in SQL would be dialect-specific for no gain at this size.
        named = [row for row in rows if metric in (row.attributed_metrics or [])]
        return named[:limit]

    def list_held_out(self, *, limit: int = 50) -> list[ReviewOutcomeRow]:
        """The reserved third, newest first, with review and question loaded.

        These are the pairs a rewritten judge is *scored* on (ADR-035). They are
        deliberately the complement of what a repair may read, which is what
        makes the score a test rather than a restatement of the training data.
        """
        stmt = (
            select(ReviewOutcomeRow)
            .options(
                joinedload(ReviewOutcomeRow.review),
                joinedload(ReviewOutcomeRow.question),
            )
            .where(ReviewOutcomeRow.held_out.is_(True))
            .order_by(ReviewOutcomeRow.created_at.desc(), ReviewOutcomeRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).unique())

    def count_by_cell(self) -> dict[QuadrantCell, int]:
        stmt = select(ReviewOutcomeRow.cell, func.count()).group_by(ReviewOutcomeRow.cell)
        return dict(self._session.execute(stmt).all())


class JudgePromptRepository:
    """Professor-edited judge prompts, and the version they imply (ADR-038)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, metric: JudgeMetricId) -> JudgePromptRow | None:
        stmt = select(JudgePromptRow).where(JudgePromptRow.metric == metric)
        return self._session.scalars(stmt).first()

    def list_all(self) -> list[JudgePromptRow]:
        stmt = select(JudgePromptRow).order_by(JudgePromptRow.metric)
        return list(self._session.scalars(stmt))

    def save(
        self,
        metric: JudgeMetricId,
        *,
        system_prompt: str,
        note: str | None,
        rules: list[dict] | None = None,
        evidence_count: int | None = None,
        learned: bool = False,
    ) -> JudgePromptRow:
        """Store one prompt, counting how often this judge has been rewritten.

        ``revision`` is per metric and informational. It is deliberately *not*
        what identifies the judge: the rubric version is a fingerprint of the
        prompts actually in force (see
        :func:`app.evaluation.judge_prompts.effective_rubric_version`), because a
        counter cannot distinguish two different prompt sets that happen to have
        been edited the same number of times.

        ``learned`` separates a model-written prompt from one the professor
        typed. A hand edit clears the rules: the professor has replaced the text
        the rules were rendered into, so continuing to claim those rules produced
        it would be false.
        """
        row = self.get(metric)
        if row is None:
            row = JudgePromptRow(metric=metric, revision=1)
            self._session.add(row)
        else:
            row.revision += 1
            row.updated_at = datetime.now(UTC)
        row.system_prompt = system_prompt
        row.note = note
        row.learned = learned
        row.rules = rules if rules is not None else []
        if evidence_count is not None:
            row.evidence_count = evidence_count
        elif not learned:
            row.evidence_count = 0
        self._session.flush()
        return row

    def delete(self, metric: JudgeMetricId) -> bool:
        """Drop one override, returning that judge to its shipped prompt."""
        row = self.get(metric)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True


class TypeInstructionRepository:
    """The learned generation instruction for each question type (ADR-033)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, question_type: QuestionType) -> TypeInstructionRow | None:
        """The stored instruction for this type, or ``None`` if none was learned.

        ``None`` is a normal answer, not an error: a type nobody has reviewed
        keeps the shipped instruction, and the caller decides that fallback.
        """
        stmt = select(TypeInstructionRow).where(TypeInstructionRow.question_type == question_type)
        return self._session.scalars(stmt).first()

    def list_all(self) -> list[TypeInstructionRow]:
        stmt = select(TypeInstructionRow).order_by(TypeInstructionRow.question_type)
        return list(self._session.scalars(stmt))

    def upsert(
        self,
        question_type: QuestionType,
        *,
        instruction: str,
        rules: list[dict],
        review_count: int,
    ) -> TypeInstructionRow:
        row = self.get(question_type)
        if row is None:
            row = TypeInstructionRow(question_type=question_type)
            self._session.add(row)
        else:
            row.updated_at = datetime.now(UTC)
        row.instruction = instruction
        row.rules = rules
        row.review_count = review_count
        self._session.flush()
        return row

    def delete(self, question_type: QuestionType) -> bool:
        """Drop one learned row, returning that type to its shipped instruction."""
        row = self.get(question_type)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True


class QuestionSetRepository:
    """Frozen snapshots of the approved bank, and the coverage query (ADR-036).

    There is deliberately no update method. A set is created whole and read
    thereafter; a snapshot that could be edited would not answer the question it
    exists to answer, which is what a given cohort was actually served.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def approved_question_ids(self, *, curriculum_version_id: int | None = None) -> list[int]:
        """Every approved question, optionally restricted to one curriculum.

        Approved means the professor approved it. A question that merely passed
        deterministic validation carries no verdict and must never reach a
        student.
        """
        stmt = select(QuestionRow.id).where(QuestionRow.status == QuestionStatus.APPROVED)
        if curriculum_version_id is not None:
            stmt = stmt.where(QuestionRow.curriculum_version_id == curriculum_version_id)
        return list(self._session.scalars(stmt.order_by(QuestionRow.id)))

    def create(
        self,
        *,
        label: str,
        question_ids: Collection[int],
        curriculum_version_id: int | None,
        notes: str | None = None,
    ) -> QuestionSetVersionRow:
        """Freeze these question ids as a new set. Never call twice for one set."""
        ids = sorted(set(question_ids))
        row = QuestionSetVersionRow(
            label=label,
            curriculum_version_id=curriculum_version_id,
            notes=notes,
            question_count=len(ids),
        )
        row.members = [QuestionSetMemberRow(question_id=question_id) for question_id in ids]
        self._session.add(row)
        self._session.flush()
        return row

    def list_versions(self, limit: int = 50) -> list[QuestionSetVersionRow]:
        stmt = (
            select(QuestionSetVersionRow)
            .options(selectinload(QuestionSetVersionRow.members))
            .order_by(QuestionSetVersionRow.created_at.desc(), QuestionSetVersionRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def get(self, set_version_id: int) -> QuestionSetVersionRow:
        """One set with its members.

        Raises:
            NotFoundError: if no such set exists.
        """
        stmt = (
            select(QuestionSetVersionRow)
            .options(selectinload(QuestionSetVersionRow.members))
            .where(QuestionSetVersionRow.id == set_version_id)
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError(f"Question set {set_version_id} was not found.")
        return row

    def coverage_counts(
        self, *, question_ids: Collection[int] | None = None
    ) -> dict[tuple[int, Difficulty], int]:
        """How many questions cover each (subtopic, difficulty) pair.

        Counts distinct questions: a question tagged with three subtopics is one
        question in each of three rows, which is what the adaptive engine would
        find when it selects on that subtopic.

        Returns only pairs that have at least one question. The empty pairs --
        the ones the professor needs -- are produced by walking the taxonomy
        against this mapping, so a subtopic with no questions at all cannot fall
        out of a join and be read as covered.
        """
        stmt = (
            select(
                QuestionSubtopicRow.subtopic_id,
                QuestionRow.difficulty,
                func.count(func.distinct(QuestionRow.id)),
            )
            .join(QuestionRow, QuestionRow.id == QuestionSubtopicRow.question_id)
            .where(QuestionRow.status == QuestionStatus.APPROVED)
            .group_by(QuestionSubtopicRow.subtopic_id, QuestionRow.difficulty)
        )
        if question_ids is not None:
            ids = list(question_ids)
            if not ids:
                return {}
            stmt = stmt.where(QuestionRow.id.in_(ids))
        return {
            (subtopic_id, Difficulty(difficulty)): count
            for subtopic_id, difficulty, count in self._session.execute(stmt)
        }

    def approved_question_counts_by_topic(
        self, *, question_ids: Collection[int] | None = None
    ) -> dict[int, int]:
        """Distinct approved questions claiming each topic.

        Counted off ``QuestionRow.topic_id`` rather than by joining through the
        subtopics, because a question claims exactly one topic (ADR-031) but up
        to three of its subtopics. Joining would multiply a question by its
        subtopics and report a topic as holding more questions than exist.
        """
        stmt = (
            select(QuestionRow.topic_id, func.count(func.distinct(QuestionRow.id)))
            .where(QuestionRow.status == QuestionStatus.APPROVED)
            .where(QuestionRow.topic_id.is_not(None))
            .group_by(QuestionRow.topic_id)
        )
        if question_ids is not None:
            ids = list(question_ids)
            if not ids:
                return {}
            stmt = stmt.where(QuestionRow.id.in_(ids))
        return dict(self._session.execute(stmt).all())  # type: ignore[arg-type]

    def count_for_curriculum_version(self, version_id: int) -> int:
        """Frozen sets tagged against this curriculum version.

        A set is immutable by decision (ADR-036) and nothing can delete one, so a
        set whose taxonomy is gone can never report coverage again.
        """
        stmt = (
            select(func.count())
            .select_from(QuestionSetVersionRow)
            .where(QuestionSetVersionRow.curriculum_version_id == version_id)
        )
        return self._session.scalar(stmt) or 0

    def servable_subtopic_ids(self, set_version_id: int) -> set[int]:
        """Subtopics this set can actually answer a request for.

        The roulette is weighted over these rather than over the whole taxonomy.
        Drawing a subtopic the set holds no question for would mean redrawing
        until one lands, which biases the draw away from exactly the subtopics
        the professor has not written for yet -- silently, and worst when the
        bank is thinnest.
        """
        stmt = (
            select(QuestionSubtopicRow.subtopic_id)
            .join(QuestionRow, QuestionRow.id == QuestionSubtopicRow.question_id)
            .join(QuestionSetMemberRow, QuestionSetMemberRow.question_id == QuestionRow.id)
            .where(
                QuestionSetMemberRow.set_version_id == set_version_id,
                QuestionRow.status == QuestionStatus.APPROVED,
            )
            .distinct()
        )
        return set(self._session.scalars(stmt))

    def candidates_for_cell(
        self, set_version_id: int, *, subtopic_id: int, difficulty: Difficulty
    ) -> list[tuple[int, int, int]]:
        """``(question_id, priority, times_used)`` for one cell of one set.

        Ordering is left to :func:`app.adaptive.selection.rank_candidates`, which
        also needs the student's own history -- something this query has no
        business knowing about.

        Approval is re-checked rather than assumed from membership. A set is
        immutable (ADR-036), but a professor can reject a question after it was
        frozen into one, and a question whose approval was withdrawn must not
        reach a student.
        """
        stmt = (
            select(QuestionRow.id, QuestionRow.priority, QuestionRow.times_used)
            .join(QuestionSetMemberRow, QuestionSetMemberRow.question_id == QuestionRow.id)
            .join(QuestionSubtopicRow, QuestionSubtopicRow.question_id == QuestionRow.id)
            .where(
                QuestionSetMemberRow.set_version_id == set_version_id,
                QuestionSubtopicRow.subtopic_id == subtopic_id,
                QuestionRow.difficulty == difficulty,
                QuestionRow.status == QuestionStatus.APPROVED,
            )
            .order_by(QuestionRow.id)
        )
        return [(row[0], row[1], row[2]) for row in self._session.execute(stmt)]


class StudentRepository:
    """Learners the adaptive engine tracks."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(StudentRow)) or 0

    def list_all(self) -> list[StudentRow]:
        stmt = select(StudentRow).order_by(StudentRow.display_name)
        return list(self._session.scalars(stmt))

    def get(self, student_id: int) -> StudentRow:
        """One student.

        Raises:
            NotFoundError: if no such student exists.
        """
        row = self._session.get(StudentRow, student_id)
        if row is None:
            raise NotFoundError(f"Student {student_id} was not found.")
        return row

    def get_by_name(self, display_name: str) -> StudentRow | None:
        stmt = select(StudentRow).where(StudentRow.display_name == display_name)
        return self._session.scalars(stmt).first()

    def add(self, display_name: str) -> StudentRow:
        row = StudentRow(display_name=display_name)
        self._session.add(row)
        self._session.flush()
        return row


class StudentStateRepository:
    """Per-student BKT mastery and subtopic weakness (ADR-041).

    Reads never create a row; writes do. An unseen topic or subtopic reads as its
    starting value, which is what "created on first touch" means -- rendering a
    progress page must not seed a hundred rows, and a bulk seed would also break
    the moment the curriculum gains a subtopic.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def mastery_for(self, student_id: int, topic_id: int) -> float:
        """Stored mastery, or the BKT prior if this topic was never scored."""
        stmt = select(StudentTopicMasteryRow.p_known).where(
            StudentTopicMasteryRow.student_id == student_id,
            StudentTopicMasteryRow.topic_id == topic_id,
        )
        stored = self._session.scalars(stmt).first()
        return DEFAULT_BKT_PARAMETERS.p_init if stored is None else stored

    def weaknesses_for(self, student_id: int, subtopic_ids: Collection[int]) -> dict[int, float]:
        """Weakness per requested subtopic, defaulting the ones never scored.

        Every requested id is present in the result, so the caller can hand the
        mapping straight to the roulette without deciding what an absent row
        means.
        """
        ids = list(subtopic_ids)
        if not ids:
            return {}
        stmt = select(
            StudentSubtopicWeaknessRow.subtopic_id, StudentSubtopicWeaknessRow.weakness
        ).where(
            StudentSubtopicWeaknessRow.student_id == student_id,
            StudentSubtopicWeaknessRow.subtopic_id.in_(ids),
        )
        stored = dict(self._session.execute(stmt).all())
        return {
            subtopic_id: stored.get(subtopic_id, INITIAL_SUBTOPIC_WEAKNESS) for subtopic_id in ids
        }

    def list_mastery(self, student_id: int) -> list[StudentTopicMasteryRow]:
        stmt = (
            select(StudentTopicMasteryRow)
            .where(StudentTopicMasteryRow.student_id == student_id)
            .order_by(StudentTopicMasteryRow.topic_id)
        )
        return list(self._session.scalars(stmt))

    def list_weakness(self, student_id: int) -> list[StudentSubtopicWeaknessRow]:
        stmt = (
            select(StudentSubtopicWeaknessRow)
            .where(StudentSubtopicWeaknessRow.student_id == student_id)
            .order_by(StudentSubtopicWeaknessRow.subtopic_id)
        )
        return list(self._session.scalars(stmt))

    def count_students_measured_on(
        self, topic_ids: Collection[int], subtopic_ids: Collection[int]
    ) -> int:
        """How many distinct students have been measured on any of these rows.

        Mastery and weakness are what the adaptive engine has learned about a
        learner (ADR-041), and nothing can rebuild them from an answer already
        given. Deleting the topics and subtopics they name leaves the values in
        place but unreadable: a progress page filters by the ids that still
        exist, so a measured subtopic simply stops appearing.
        """
        topics = list(topic_ids)
        subtopics = list(subtopic_ids)
        measured: set[int] = set()
        if topics:
            stmt = select(StudentTopicMasteryRow.student_id).where(
                StudentTopicMasteryRow.topic_id.in_(topics)
            )
            measured.update(self._session.scalars(stmt))
        if subtopics:
            stmt = select(StudentSubtopicWeaknessRow.student_id).where(
                StudentSubtopicWeaknessRow.subtopic_id.in_(subtopics)
            )
            measured.update(self._session.scalars(stmt))
        return len(measured)

    def record_mastery(
        self, student_id: int, topic_id: int, p_known: float
    ) -> StudentTopicMasteryRow:
        """Store a new mastery for this topic, creating the row if needed."""
        stmt = select(StudentTopicMasteryRow).where(
            StudentTopicMasteryRow.student_id == student_id,
            StudentTopicMasteryRow.topic_id == topic_id,
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            row = StudentTopicMasteryRow(student_id=student_id, topic_id=topic_id)
            self._session.add(row)
        else:
            row.updated_at = datetime.now(UTC)
        row.p_known = p_known
        row.observations = (row.observations or 0) + 1
        self._session.flush()
        return row

    def record_weakness(
        self, student_id: int, subtopic_id: int, weakness: float
    ) -> StudentSubtopicWeaknessRow:
        """Store a new weakness for this subtopic, creating the row if needed."""
        stmt = select(StudentSubtopicWeaknessRow).where(
            StudentSubtopicWeaknessRow.student_id == student_id,
            StudentSubtopicWeaknessRow.subtopic_id == subtopic_id,
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            row = StudentSubtopicWeaknessRow(student_id=student_id, subtopic_id=subtopic_id)
            self._session.add(row)
        else:
            row.updated_at = datetime.now(UTC)
        row.weakness = weakness
        row.observations = (row.observations or 0) + 1
        self._session.flush()
        return row


class TrainingSessionRepository:
    """A student's run against one frozen question set (ADR-036)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, student_id: int, set_version_id: int, rng_seed: int) -> TrainingSessionRow:
        row = TrainingSessionRow(
            student_id=student_id, set_version_id=set_version_id, rng_seed=rng_seed
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get(self, session_id: int) -> TrainingSessionRow:
        """One session.

        Raises:
            NotFoundError: if no such session exists.
        """
        row = self._session.get(TrainingSessionRow, session_id)
        if row is None:
            raise NotFoundError(f"Training session {session_id} was not found.")
        return row

    def list_for_student(self, student_id: int, limit: int = 50) -> list[TrainingSessionRow]:
        stmt = (
            select(TrainingSessionRow)
            .where(TrainingSessionRow.student_id == student_id)
            .order_by(TrainingSessionRow.created_at.desc(), TrainingSessionRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def end(self, row: TrainingSessionRow) -> TrainingSessionRow:
        row.ended_at = datetime.now(UTC)
        self._session.flush()
        return row


class StudentAttemptRepository:
    """Questions served to students, and the scores they came back with."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, row: StudentAttemptRow) -> StudentAttemptRow:
        self._session.add(row)
        self._session.flush()
        return row

    def count_on_subtopics(self, subtopic_ids: Collection[int]) -> int:
        """Attempts served for any of these subtopics.

        Part of the cost of deleting a curriculum version: the attempt row keeps
        its score and its question, but the subtopic it was drawn for stops
        resolving.
        """
        ids = list(subtopic_ids)
        if not ids:
            return 0
        stmt = (
            select(func.count())
            .select_from(StudentAttemptRow)
            .where(StudentAttemptRow.subtopic_id.in_(ids))
        )
        return self._session.scalar(stmt) or 0

    def get(self, attempt_id: int) -> StudentAttemptRow:
        """One attempt.

        Raises:
            NotFoundError: if no such attempt exists.
        """
        row = self._session.get(StudentAttemptRow, attempt_id)
        if row is None:
            raise NotFoundError(f"Attempt {attempt_id} was not found.")
        return row

    def next_ordinal(self, session_id: int) -> int:
        """Position for the next question in this session, counting from 1."""
        stmt = select(func.max(StudentAttemptRow.ordinal)).where(
            StudentAttemptRow.session_id == session_id
        )
        return (self._session.scalar(stmt) or 0) + 1

    def open_attempt(self, session_id: int) -> StudentAttemptRow | None:
        """The question this session is waiting on an answer for, if any.

        Serving a second question while one is unanswered would leave the first
        permanently open and let a student skip anything they disliked, which is
        a selection bias the mastery estimate cannot see.
        """
        stmt = (
            select(StudentAttemptRow)
            .where(
                StudentAttemptRow.session_id == session_id,
                StudentAttemptRow.score.is_(None),
            )
            .order_by(StudentAttemptRow.ordinal.desc())
        )
        return self._session.scalars(stmt).first()

    def answered_question_ids(self, student_id: int) -> set[int]:
        """Every question this student has already scored, across all sessions.

        Feeds ADR-041's per-student ordering key. Scoped to the student and not
        to the session: meeting the same question again in a new session is the
        same repeat.
        """
        stmt = (
            select(StudentAttemptRow.question_id)
            .where(
                StudentAttemptRow.student_id == student_id,
                StudentAttemptRow.score.is_not(None),
            )
            .distinct()
        )
        return set(self._session.scalars(stmt))

    def list_for_session(self, session_id: int) -> list[StudentAttemptRow]:
        stmt = (
            select(StudentAttemptRow)
            .options(joinedload(StudentAttemptRow.question))
            .where(StudentAttemptRow.session_id == session_id)
            .order_by(StudentAttemptRow.ordinal)
        )
        return list(self._session.scalars(stmt))

    def list_for_student(self, student_id: int, limit: int = 100) -> list[StudentAttemptRow]:
        stmt = (
            select(StudentAttemptRow)
            .options(joinedload(StudentAttemptRow.question))
            .where(StudentAttemptRow.student_id == student_id)
            .order_by(StudentAttemptRow.created_at.desc(), StudentAttemptRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def count_answered(self, student_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(StudentAttemptRow)
            .where(
                StudentAttemptRow.student_id == student_id,
                StudentAttemptRow.score.is_not(None),
            )
        )
        return self._session.scalar(stmt) or 0
