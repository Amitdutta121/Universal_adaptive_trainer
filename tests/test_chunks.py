"""Chunks: the table, deterministic ids, versions and the repository (Task 4)."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session

from app.domain.chunks import Chunk, make_chunk_id
from app.errors import NotFoundError
from app.persistence.database import _alembic_config
from app.persistence.models import BookRow, ChunkRow
from app.persistence.repositories import BookRepository, ChunkRepository


def _book(session: Session, title: str = "Agah") -> BookRow:
    return BookRepository(session).add(BookRow(title=title, original_filename="agah.pdf"))


def _draft(text: str, start: int | None, end: int | None, *path: str) -> ChunkRow:
    return ChunkRow(text=text, page_start=start, page_end=end, heading_path=list(path))


def test_a_version_gets_ordinals_ids_and_becomes_current(session: Session) -> None:
    book = _book(session)
    repo = ChunkRepository(session)

    version = repo.add_version(
        book, [_draft("Loops repeat.", 3, 3, "4. Loops"), _draft("Nested.", 3, 4, "4. Loops")]
    )
    session.commit()

    assert version == 1
    assert book.current_version == 1
    rows = repo.list_for_book(book.id)
    assert [row.ordinal for row in rows] == [0, 1]
    assert rows[0].id == make_chunk_id(book.id, 1, 0, "Loops repeat.")
    assert len(rows[0].content_hash) == 64


def test_ids_are_deterministic_and_differ_by_version() -> None:
    assert make_chunk_id(1, 1, 0, "x") == make_chunk_id(1, 1, 0, "x")
    assert make_chunk_id(1, 1, 0, "x") != make_chunk_id(1, 2, 0, "x")
    assert len(make_chunk_id(1, 1, 0, "x")) == 32


def test_a_new_version_keeps_the_old_chunks_resolvable(session: Session) -> None:
    book = _book(session)
    repo = ChunkRepository(session)
    repo.add_version(book, [_draft("Old text.", 1, 1)])
    old_id = repo.list_for_book(book.id)[0].id

    assert repo.add_version(book, [_draft("New text.", 1, 1)]) == 2
    session.commit()

    assert [row.text for row in repo.list_for_book(book.id)] == ["New text."]
    assert repo.get(old_id).text == "Old text."
    assert [row.text for row in repo.list_for_book(book.id, version=1)] == ["Old text."]
    assert repo.count(book.id) == 1


def test_list_by_page_returns_the_chunks_covering_it(session: Session) -> None:
    book = _book(session)
    repo = ChunkRepository(session)
    repo.add_version(
        book,
        [_draft("a", 1, 1), _draft("b", 1, 2), _draft("c", 2, 2), _draft("d", 3, None)],
    )

    assert [row.text for row in repo.list_for_book(book.id, page=2)] == ["b", "c"]
    assert [row.text for row in repo.list_for_book(book.id, page=3)] == ["d"]
    assert repo.list_for_book(book.id, page=9) == []


def test_a_book_without_chunks_lists_nothing(session: Session) -> None:
    book = _book(session)
    assert ChunkRepository(session).list_for_book(book.id) == []
    assert ChunkRepository(session).count(book.id) == 0


def test_get_raises_for_a_missing_chunk(session: Session) -> None:
    with pytest.raises(NotFoundError):
        ChunkRepository(session).get("0" * 32)


def test_get_many_skips_missing_ids(session: Session) -> None:
    book = _book(session)
    repo = ChunkRepository(session)
    repo.add_version(book, [_draft("a", 1, 1)])
    real = repo.list_for_book(book.id)[0].id

    assert set(repo.get_many([real, "missing"])) == {real}


def test_deleting_the_book_deletes_its_chunks(session: Session) -> None:
    book = _book(session)
    ChunkRepository(session).add_version(book, [_draft("a", 1, 1)])
    session.commit()

    BookRepository(session).delete(book)
    session.commit()

    assert session.query(ChunkRow).count() == 0


def test_citation_names_book_heading_path_and_pages() -> None:
    chunk = Chunk(
        id="x",
        book_id=1,
        book_version=1,
        ordinal=0,
        page_start=33,
        page_end=34,
        heading_path=["4. Repetitions", "4.4. Nested Loops"],
        text="...",
        book_title="Agah",
    )
    assert chunk.citation() == "Agah, 4. Repetitions \u203a 4.4. Nested Loops (Pages 33\u201334)"
    pageless = chunk.model_copy(update={"page_start": None, "page_end": None, "heading_path": []})
    assert pageless.citation() == "Agah"


def test_the_migration_downgrades_and_upgrades_cleanly(engine: Engine) -> None:
    with engine.begin() as connection:
        config = _alembic_config(connection)
        command.downgrade(config, "0021_solve_flag")
        assert "chunks" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert "chunks" in inspect(connection).get_table_names()
        columns = {column["name"] for column in inspect(connection).get_columns("books")}
        assert "current_version" in columns
