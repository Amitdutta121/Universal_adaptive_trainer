"""Managing an imported book: its labels, and its removal.

Separate from :mod:`app.ingestion.service`, which is the import workflow. Import
is about a document; this is about the row that document produced, after the fact.

What may be edited
    The labels only -- title, author, notes. Structure is declared by the imported
    document (ADR-015), so a wrong chapter boundary is corrected by fixing the
    document and importing it again, never by editing rows here. Allowing a
    structural edit would break the promise that a book's structure is exactly
    what its retained document says.

What deleting costs
    A question records the sections it was generated from inside its frozen
    ``QuestionSpec``, not as a foreign key (ADR-036). Deleting a book therefore
    cannot cascade to its questions, and nothing repairs their citation: it simply
    points at sections that no longer exist. So deletion refuses by default while
    any question cites the book, names the count, and proceeds only when the
    professor repeats the request with ``force``.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.errors import DomainRuleError, ResourceInUseError
from app.ingestion.storage import resolve_stored_path
from app.persistence.models import BookRow
from app.persistence.repositories import BookRepository, QuestionRepository

logger = logging.getLogger(__name__)


class BookLibraryService:
    """Rename and delete books that are already imported."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._books = BookRepository(session)
        self._questions = QuestionRepository(session)

    def grounded_question_count(self, book_id: int) -> int:
        """How many questions were generated from this book's sections.

        Zero for a book nothing has been generated from yet, which is the common
        case and the one where deleting is free.
        """
        return self._questions.count_grounded_in_sections(self._books.section_ids(book_id))

    def update_metadata(
        self,
        book_id: int,
        *,
        title: str | None = None,
        author: str | None = None,
        notes: str | None = None,
    ) -> BookRow:
        """Edit a book's labels, leaving every omitted field as it was.

        ``author`` and ``notes`` are cleared by passing an empty string, because
        "this book has no author printed" is a real correction. ``title`` is not:
        a book row must stay identifiable in a list, so a blank title is refused
        rather than accepted and rendered as an empty link.

        Raises:
            NotFoundError: no such book.
            DomainRuleError: the title was given as blank.
        """
        book = self._books.get(book_id)

        if title is not None:
            cleaned = title.strip()
            if not cleaned:
                raise DomainRuleError(
                    "A book must keep a title.",
                    detail="Leave the title unchanged, or give it a new one.",
                )
            book.title = cleaned
        if author is not None:
            book.author = author.strip() or None
        if notes is not None:
            book.notes = notes.strip() or None

        self._session.flush()
        logger.info("Updated book %s labels", book_id)
        return book

    def delete(self, book_id: int, *, force: bool = False) -> int:
        """Delete a book, its chapters and sections, and its retained document.

        Args:
            book_id: the book to remove.
            force: proceed even though questions cite this book. Their citations
                are stranded, deliberately and with the count already reported.

        Returns:
            How many questions were left citing sections that no longer exist.
            Zero unless ``force`` overrode a refusal.

        Raises:
            NotFoundError: no such book.
            ResourceInUseError: questions cite this book and ``force`` is False.
        """
        book = self._books.get(book_id)
        grounded = self.grounded_question_count(book_id)

        if grounded and not force:
            raise ResourceInUseError(
                f"{grounded} question{'' if grounded == 1 else 's'} were generated from this book.",
                detail=(
                    "Deleting it does not delete them; it leaves their source citation "
                    "pointing at sections that no longer exist. Repeat the request with "
                    "force=true to delete the book anyway."
                ),
            )

        self._delete_retained_document(book)
        self._books.delete(book)
        logger.info("Deleted book %s, stranding %d question citation(s)", book_id, grounded)
        return grounded

    def _delete_retained_document(self, book: BookRow) -> None:
        """Remove the uploaded file this book was imported from.

        The document is retained so an import is reproducible (ADR-013); once the
        import it reproduces is gone, keeping the file leaves an orphan nothing
        can be traced back to. A file that is already missing is not an error --
        the row is going regardless, and failing here would leave the professor
        with a book they cannot delete.
        """
        if not book.stored_filename:
            return
        path = resolve_stored_path(book.stored_filename, self._settings)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete retained document %s", path, exc_info=True)
