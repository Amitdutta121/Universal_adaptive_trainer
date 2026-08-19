"""Managing an imported taxonomy: its display names, and its removal.

Separate from :mod:`app.curriculum.taxonomy_import`, which is the import
workflow. Import is about a document; this is about the rows that document
produced, after the fact.

What may be edited
    Display names and descriptions only -- the version's label, and each topic's
    and subtopic's name and description. Which topics exist, and which subtopics
    hang off which topic, is declared by the uploaded document (ADR-021), so a
    wrong grouping is corrected by fixing the document and uploading it again.

Why a rename is safe, and why the id then stops matching the name
    ``stable_id`` is assigned at import from the name as it then stood
    (:mod:`app.curriculum.taxonomy_ids`) and is never recomputed here. That is
    what keeps a student's measured weakness and a question's tagging attached to
    the same row across a rename, which is exactly the promise ADR-021 makes. The
    consequence is that after a rename the id no longer equals a hash of the
    current name -- and that is correct. The id is an identity, not a checksum:
    it records the name the concept was imported under. Recomputing it would
    detach every measurement taken under the old id.

The one check books did not need
    The upload validator refuses two topics whose normalised names collide, and a
    rename can reintroduce that collision with the validator out of the path. So
    a rename re-applies the same rule against the siblings already stored, using
    the same :func:`normalize_label` -- never a second implementation of the
    comparison.

What deleting costs
    Far more than deleting a book, and the difference is not visible in the
    schema. ``models.py`` declares ``ondelete`` on every foreign key into the
    curriculum tree, but SQLite enforces none of it: the engine sets no
    ``PRAGMA foreign_keys`` (:mod:`app.persistence.database`), so what actually
    runs is SQLAlchemy's own cascade -- version, topics, subtopics, evidence, and
    nothing else. Questions, question sets, student mastery, student weakness and
    attempts keep integers pointing at rows that no longer exist. They are
    counted and reported before the decision, and never repaired afterwards.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.curriculum.stable_ids import normalize_label
from app.domain.enums import CurriculumStatus
from app.errors import DomainRuleError, ResourceInUseError, UnoverridableConflictError
from app.persistence.models import CurriculumVersionRow, SubtopicRow, TopicRow
from app.persistence.repositories import (
    CurriculumRepository,
    QuestionRepository,
    QuestionSetRepository,
    StudentAttemptRepository,
    StudentStateRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurriculumUsage:
    """What still points at a curriculum version, and how much of it is unrepairable."""

    question_count: int
    question_subtopic_link_count: int
    #: Frozen sets built against this version (ADR-036). Deleting is refused
    #: outright while this is non-zero.
    question_set_count: int
    student_count: int
    attempt_count: int
    #: Whether ``GET /api/curriculum/approved`` currently returns this version.
    is_approved: bool

    @property
    def strandable(self) -> bool:
        """Whether anything would be left pointing at deleted rows."""
        return bool(
            self.question_count
            or self.question_subtopic_link_count
            or self.student_count
            or self.attempt_count
        )


class CurriculumLibraryService:
    """Rename and delete curriculum versions that are already imported."""

    def __init__(self, session: Session) -> None:
        # No Settings, unlike the book library: a taxonomy upload retains no file,
        # so there is nothing on disk to remove alongside the rows.
        self._session = session
        self._curriculum = CurriculumRepository(session)
        self._questions = QuestionRepository(session)
        self._sets = QuestionSetRepository(session)
        self._state = StudentStateRepository(session)
        self._attempts = StudentAttemptRepository(session)

    # ------------------------------------------------------------------ editing

    def update_version_label(self, version_id: int, *, label: str) -> CurriculumVersionRow:
        """Rename a version, leaving its status and its tree untouched.

        Raises:
            NotFoundError: no such version.
            DomainRuleError: the label was given as blank.
        """
        version = self._curriculum.get_version(version_id)
        version.label = _required_label(label, "curriculum version", "label")
        self._session.flush()
        logger.info("Renamed curriculum version %s", version_id)
        return version

    def update_topic(
        self, topic_id: int, *, name: str | None = None, description: str | None = None
    ) -> TopicRow:
        """Edit a topic's display name and description.

        Raises:
            NotFoundError: no such topic.
            DomainRuleError: a blank name, or a name a sibling topic already uses.
        """
        topic = self._curriculum.get_topic(topic_id)
        if name is not None:
            cleaned = _required_label(name, "topic", "name")
            _refuse_duplicate(
                cleaned,
                self._curriculum.sibling_topic_names(
                    topic.curriculum_version_id, exclude_topic_id=topic_id
                ),
                "topic",
                "this curriculum version",
            )
            topic.name = cleaned
        if description is not None:
            topic.description = description.strip() or None
        self._session.flush()
        logger.info("Renamed topic %s", topic_id)
        return topic

    def update_subtopic(
        self, subtopic_id: int, *, name: str | None = None, description: str | None = None
    ) -> SubtopicRow:
        """Edit a subtopic's display name and description.

        Raises:
            NotFoundError: no such subtopic.
            DomainRuleError: a blank name, or a name a sibling subtopic already uses.
        """
        subtopic = self._curriculum.get_subtopic(subtopic_id)
        if name is not None:
            cleaned = _required_label(name, "subtopic", "name")
            _refuse_duplicate(
                cleaned,
                self._curriculum.sibling_subtopic_names(
                    subtopic.topic_id, exclude_subtopic_id=subtopic_id
                ),
                "subtopic",
                "this topic",
            )
            subtopic.name = cleaned
        if description is not None:
            subtopic.description = description.strip() or None
        self._session.flush()
        logger.info("Renamed subtopic %s", subtopic_id)
        return subtopic

    def activate(self, version_id: int) -> CurriculumVersionRow:
        """Make an already-approved taxonomy the live one again.

        Uploading a new taxonomy approves it immediately, but a professor may
        later decide an older approved upload should be the one generation and
        coverage use. That decision is recorded by advancing ``approved_at`` so
        the active version is explicit and auditable.

        Raises:
            NotFoundError: no such version.
            DomainRuleError: the version was never approved and cannot become
                active by this route.
        """
        version = self._curriculum.get_version(version_id)
        if version.status is not CurriculumStatus.APPROVED:
            raise DomainRuleError(
                "Only an approved curriculum version can be made active.",
                detail="Upload a valid taxonomy, or choose one that was approved already.",
            )
        current = self._curriculum.get_approved()
        if current is not None and current.id == version_id:
            return version
        candidate = _sqlite_orderable_utc(datetime.now(UTC))
        current_approved_at = (
            _sqlite_orderable_utc(current.approved_at)
            if current is not None and current.approved_at is not None
            else None
        )
        if current is not None and current_approved_at is not None:
            current.approved_at = current_approved_at
        if current_approved_at is not None and candidate <= current_approved_at:
            candidate = current_approved_at + timedelta(microseconds=1)
        version.approved_at = candidate
        self._session.flush()
        logger.info("Activated curriculum version %s", version_id)
        return version

    # ------------------------------------------------------------------ removal

    def usage(self, version_id: int) -> CurriculumUsage:
        """What points at this version, counted before anything is decided."""
        topic_ids = self._curriculum.topic_ids_in(version_id)
        subtopic_ids = self._curriculum.subtopic_ids_in(version_id)
        approved = self._curriculum.get_approved()
        return CurriculumUsage(
            question_count=self._questions.count_for_curriculum_version(version_id),
            question_subtopic_link_count=self._questions.count_subtopic_links(subtopic_ids),
            question_set_count=self._sets.count_for_curriculum_version(version_id),
            student_count=self._state.count_students_measured_on(topic_ids, subtopic_ids),
            attempt_count=self._attempts.count_on_subtopics(subtopic_ids),
            is_approved=approved is not None and approved.id == version_id,
        )

    def delete(self, version_id: int, *, force: bool = False) -> CurriculumUsage:
        """Delete a version and its topics, subtopics and evidence.

        Two refusals have no ``force`` path, because there is no professor
        judgement left for one to express:

        * **a frozen question set names this version.** A set is immutable and
          nothing can delete one (ADR-036), so its coverage report would raise
          for good. Unlike a book citation, this cannot even be cleaned up.
        * **this is the approved version.** Deleting it would either stop
          generation outright or, worse, silently re-ground the product on
          whichever version ``approved_at`` finds next. The remedy is always
          available and is one step: upload a replacement, which becomes approved
          immediately (ADR-021), after which this version is deletable.

        ``force`` therefore covers exactly one case: a superseded version with
        questions or student measurements hanging off it and no frozen set.

        Args:
            version_id: the version to remove.
            force: proceed even though questions and students would be left
                pointing at deleted rows. Their references are stranded,
                deliberately and with the counts already reported.

        Returns:
            The usage as it stood at deletion -- every count in it is now dangling.

        Raises:
            NotFoundError: no such version.
            UnoverridableConflictError: a frozen set names it, or it is the
                approved version -- neither of which ``force`` can override.
            ResourceInUseError: it has dependants and ``force`` is False.
        """
        version = self._curriculum.get_version(version_id)
        usage = self.usage(version_id)

        if usage.question_set_count:
            raise UnoverridableConflictError(
                f"{_count(usage.question_set_count, 'frozen question set')} "
                f"{'names' if usage.question_set_count == 1 else 'name'} this curriculum version.",
                detail=(
                    "A question set is a frozen record of what a cohort was served, and "
                    "nothing can edit or delete one. Without this taxonomy its coverage "
                    "can never be reported again, so this cannot be overridden."
                ),
            )

        if usage.is_approved:
            raise UnoverridableConflictError(
                "This is the approved curriculum version.",
                detail=(
                    "Question generation is grounded in it, and deleting it would leave "
                    "the product grounded in whichever version was approved before, "
                    "without anyone deciding that. Upload a replacement taxonomy first "
                    "-- it becomes approved immediately -- then delete this one."
                ),
            )

        if usage.strandable and not force:
            raise ResourceInUseError(
                _dependants_sentence(usage),
                detail=(
                    "Deleting this version does not delete them; it leaves them naming "
                    "topics and subtopics that no longer exist, and a student's measured "
                    "mastery and weakness cannot be rebuilt. Repeat the request with "
                    "force=true to delete it anyway."
                ),
            )

        if version.status is not CurriculumStatus.APPROVED:
            logger.info("Deleting %s curriculum version %s", version.status.value, version_id)
        self._curriculum.delete(version)
        logger.info(
            "Deleted curriculum version %s, stranding %d question(s) and %d student(s)",
            version_id,
            usage.question_count,
            usage.student_count,
        )
        return usage


def _count(value: int, noun: str) -> str:
    return f"{value} {noun}{'' if value == 1 else 's'}"


def _dependants_sentence(usage: CurriculumUsage) -> str:
    """Name everything that would be stranded, so the count is in front of the decision."""
    parts = []
    if usage.question_count:
        parts.append(_count(usage.question_count, "question"))
    if usage.question_subtopic_link_count:
        parts.append(_count(usage.question_subtopic_link_count, "subtopic tagging"))
    if usage.student_count:
        parts.append(_count(usage.student_count, "student"))
    if usage.attempt_count:
        parts.append(_count(usage.attempt_count, "attempt"))
    return f"{', '.join(parts)} still point at this curriculum version."


def _required_label(value: str, what: str, field: str) -> str:
    """Trim a label that may not be blank, or refuse.

    A blank name is refused rather than stored because these rows have to stay
    identifiable in a list -- and because a subtopic's name is what the generator
    and the four judges are shown when a question is classified against it.
    """
    cleaned = value.strip()
    if not cleaned:
        raise DomainRuleError(
            f"A {what} must keep a {field}.",
            detail=f"Leave the {field} unchanged, or give it a new one.",
        )
    return cleaned


def _sqlite_orderable_utc(value: datetime) -> datetime:
    """Normalize a datetime to naive UTC, which is how SQLite returns it here."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _refuse_duplicate(name: str, siblings: list[str], what: str, where: str) -> None:
    """Refuse a rename that collides with a sibling, by the document's own rule.

    Comparison goes through :func:`normalize_label`, the same function the upload
    validator uses, so two spellings of one name are as unacceptable after a
    rename as they are inside a document.
    """
    key = normalize_label(name)
    for sibling in siblings:
        if normalize_label(sibling) == key:
            raise DomainRuleError(
                f"Another {what} in {where} is already called {sibling!r}.",
                detail=(
                    "Names are compared ignoring case, spacing and punctuation, so these "
                    "two would be the same name. Choose a different one."
                ),
            )
