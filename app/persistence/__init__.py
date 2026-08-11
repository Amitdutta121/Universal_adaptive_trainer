"""Persistence boundary.

Everything that touches the database lives here. Other subsystems depend on the
repositories in :mod:`app.persistence.repositories` and never build SQL or open
sessions themselves.

Scope so far: the tables the professor pipeline already needs (books, book
chapters, book sections, curriculum versions, topics, subtopics, questions,
professor reviews). Student progress tables (BKT state, subtopic weakness,
attempts) are deliberately absent until the adaptive engine is implemented --
see ``docs/DECISIONS.md``.
"""

from app.persistence.database import (
    Base,
    get_session,
    init_db,
    session_scope,
    verify_schema,
)

__all__ = ["Base", "get_session", "init_db", "session_scope", "verify_schema"]
