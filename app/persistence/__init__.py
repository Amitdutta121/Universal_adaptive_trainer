"""Persistence boundary.

Everything that touches the database lives here. Other subsystems depend on the
repositories in :mod:`app.persistence.repositories` and never build SQL or open
sessions themselves.

Scope so far: the tables the professor pipeline needs (books, book chapters,
book sections, curriculum versions, topics, subtopics, questions, professor
reviews), and the student progress tables the adaptive engine needs (students,
training sessions, BKT topic mastery, subtopic weakness, attempts) -- see
ADR-041 in ``docs/DECISIONS.md``. The engine that writes to the second group is
still being built; the tables exist ahead of it.
"""

from app.persistence.database import (
    Base,
    get_session,
    init_db,
    session_scope,
    verify_schema,
)

__all__ = ["Base", "get_session", "init_db", "session_scope", "verify_schema"]
