"""Column types that store JSON but hand back Python values.

Why these exist
    Sixteen columns hold JSON. Before these types each was a plain ``Text``
    column that every reader decoded for itself, so the same ``json.loads`` /
    ``isinstance`` / "tolerate an unreadable row" logic was written out at every
    call site -- and the copies were free to disagree. Decoding belongs to the
    column, once.

Why ``TypeDecorator`` over ``Text`` rather than :class:`sqlalchemy.JSON`
    The stored text and the emitted DDL stay exactly what they were, so an
    existing database file keeps working untouched. That matters because this
    project has no migration tool yet (``docs/DECISIONS.md`` ADR-008): a change
    that altered column types would mean "delete your database", and professor
    reviews are append-only history that must not be deleted.

Tolerance policy
    An undecodable value yields the empty result for its shape (``None`` for an
    object, ``[]`` for a list) and logs a warning. Persisted display data must
    not be able to break the page a professor came to read. These columns are
    only ever written by this application, so an unreadable value means a
    hand-edited row or a superseded format -- never untrusted input that should
    be reported as a validation failure.

Mutation is not tracked
    Assign a new value to change a column; mutating the returned list, dict or
    model in place will not be persisted. Every writer in this codebase already
    assigns, which is why no ``MutableDict`` wrapper is used here.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import Dialect, String, Text
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)


def _decode(value: str | None, *, kind: str) -> Any:
    """Parse stored JSON, returning ``None`` when it cannot be read."""
    if value is None or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        logger.warning("Discarding unreadable %s payload", kind)
        return None


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class JsonObject(TypeDecorator[dict]):
    """A JSON object. Reads as ``None`` when absent, unreadable or not an object."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: dict | None, dialect: Dialect) -> str | None:
        return None if value is None else _dump(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> dict | None:
        decoded = _decode(value, kind="JSON object")
        return decoded if isinstance(decoded, dict) else None


class JsonList(TypeDecorator[list]):
    """A JSON array. Reads as ``[]`` when absent, unreadable or not an array."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: list | None, dialect: Dialect) -> str:
        return _dump(list(value or []))

    def process_result_value(self, value: str | None, dialect: Dialect) -> list:
        decoded = _decode(value, kind="JSON array")
        return decoded if isinstance(decoded, list) else []


class PydanticObject(TypeDecorator[BaseModel]):
    """A single validated Pydantic model. ``None`` when absent or invalid."""

    impl = Text
    cache_ok = True

    def __init__(self, model: type[BaseModel]) -> None:
        # The attribute is named for the constructor parameter so SQLAlchemy can
        # build this type's cache key by introspection.
        super().__init__()
        self.model = model

    def process_bind_param(self, value: BaseModel | None, dialect: Dialect) -> str | None:
        return None if value is None else value.model_dump_json()

    def process_result_value(self, value: str | None, dialect: Dialect) -> BaseModel | None:
        decoded = _decode(value, kind=self.model.__name__)
        if decoded is None:
            return None
        try:
            return self.model.model_validate(decoded)
        except ValidationError:
            logger.warning("Discarding %s payload that no longer validates", self.model.__name__)
            return None


class PydanticList(TypeDecorator[list]):
    """A list of validated Pydantic models. Items that no longer validate are dropped."""

    impl = Text
    cache_ok = True

    def __init__(self, model: type[BaseModel]) -> None:
        super().__init__()
        self.model = model

    def process_bind_param(self, value: list[BaseModel] | None, dialect: Dialect) -> str:
        return _dump([item.model_dump(mode="json") for item in value or []])

    def process_result_value(self, value: str | None, dialect: Dialect) -> list[BaseModel]:
        decoded = _decode(value, kind=f"{self.model.__name__} list")
        if not isinstance(decoded, list):
            return []
        items: list[BaseModel] = []
        for item in decoded:
            try:
                items.append(self.model.model_validate(item))
            except ValidationError:
                logger.warning("Dropping %s item that no longer validates", self.model.__name__)
        return items


class StrEnumType(TypeDecorator[Enum]):
    """A :class:`~enum.StrEnum` stored as its value and read back as the member.

    Backing a ``Mapped[SomeEnum]`` attribute with a bare ``String`` makes the
    annotation true only half the time: a row the application just constructed
    holds the member, and the same row loaded back holds a plain ``str``. The
    two behave alike under ``str()`` and ``==``, so the difference stays hidden
    until something reads ``.value`` and raises ``AttributeError`` -- which is
    why call sites had grown ``hasattr(value, "value")`` guards.

    An unrecognised stored value raises rather than degrading quietly: unlike
    the display columns above, this is a mismatch between the schema and the
    code, and naming it is more useful than rendering a page around it.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_type: type[Enum], length: int = 32) -> None:
        super().__init__(length=length)
        self.enum_type = enum_type

    def process_bind_param(self, value: Enum | str | None, dialect: Dialect) -> str | None:
        return None if value is None else str(self.enum_type(value).value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Enum | None:
        return None if value is None else self.enum_type(value)


class EnumList(TypeDecorator[list]):
    """A list of enum members stored as their values. Unknown values are dropped.

    Dropping rather than raising is deliberate: an unrecognised value can only
    come from a member this application removed, and a retired rejection reason
    must not turn the feedback page into a 500.
    """

    impl = Text
    cache_ok = True

    def __init__(self, enum_type: type[Enum]) -> None:
        super().__init__()
        self.enum_type = enum_type

    def process_bind_param(self, value: list[Enum] | None, dialect: Dialect) -> str:
        return _dump([member.value for member in value or []])

    def process_result_value(self, value: str | None, dialect: Dialect) -> list[Enum]:
        decoded = _decode(value, kind=f"{self.enum_type.__name__} list")
        if not isinstance(decoded, list):
            return []
        members: list[Enum] = []
        for item in decoded:
            try:
                members.append(self.enum_type(item))
            except ValueError:
                logger.warning("Dropping unknown %s value %r", self.enum_type.__name__, item)
        return members
