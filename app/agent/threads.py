"""Saved conversations with the course assistant (ADR-075).

The chat panel holds a conversation as AG-UI messages and saves the whole list after each
run, under the AG-UI thread id it chose. A thread belongs to one course and one professor;
nothing in the app reads a thread's messages except the panel that reopens it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import DomainRuleError, NotFoundError
from app.persistence.models import AgentThreadRow

#: A thread's messages as stored JSON; a longer conversation is refused, not truncated.
MAX_THREAD_CHARS = 5_000_000
TITLE_CHARS = 80
UNTITLED = "New chat"


def _text_of(content: Any) -> str:
    """A user message's text: AG-UI content is a string or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


def title_for(messages: list[dict[str, Any]]) -> str:
    """The first user message, on one line and cut to :data:`TITLE_CHARS`."""
    for message in messages:
        if message.get("role") == "user":
            text = " ".join(_text_of(message.get("content")).split())
            if text:
                return text if len(text) <= TITLE_CHARS else f"{text[: TITLE_CHARS - 1]}…"
    return UNTITLED


def list_threads(session: Session, course_id: int, owner_id: uuid.UUID) -> list[AgentThreadRow]:
    """The professor's threads in this course, most recently used first."""
    return list(
        session.scalars(
            select(AgentThreadRow)
            .where(AgentThreadRow.course_id == course_id, AgentThreadRow.owner_id == owner_id)
            .order_by(AgentThreadRow.updated_at.desc())
        )
    )


def get_thread(
    session: Session, thread_id: uuid.UUID, course_id: int, owner_id: uuid.UUID
) -> AgentThreadRow:
    """One thread, or not-found when it is another course's or another professor's."""
    row = session.get(AgentThreadRow, str(thread_id))
    if row is None or row.course_id != course_id or row.owner_id != owner_id:
        raise NotFoundError(f"Chat {thread_id} does not exist.")
    return row


def save_thread(
    session: Session,
    thread_id: uuid.UUID,
    course_id: int,
    owner_id: uuid.UUID,
    messages: list[dict[str, Any]],
) -> AgentThreadRow:
    """Create the thread or replace its messages. The title follows the first user message.

    Raises:
        NotFoundError: the id belongs to another course's or another professor's thread.
        DomainRuleError: the conversation is longer than :data:`MAX_THREAD_CHARS`.
    """
    if len(json.dumps(messages)) > MAX_THREAD_CHARS:
        raise DomainRuleError("This chat is too long to save. Start a new chat.")
    row = session.get(AgentThreadRow, str(thread_id))
    if row is None:
        row = AgentThreadRow(id=str(thread_id), course_id=course_id, owner_id=owner_id)
        session.add(row)
    elif row.course_id != course_id or row.owner_id != owner_id:
        raise NotFoundError(f"Chat {thread_id} does not exist.")
    row.messages = messages
    row.title = title_for(messages)
    session.commit()
    return row


def delete_thread(
    session: Session, thread_id: uuid.UUID, course_id: int, owner_id: uuid.UUID
) -> None:
    session.delete(get_thread(session, thread_id, course_id, owner_id))
    session.commit()
