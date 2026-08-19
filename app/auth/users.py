"""The professor user table, its manager, and the FastAPI dependencies that build them."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.persistence.async_database import get_async_session
from app.persistence.models import UserRow

logger = logging.getLogger(__name__)


async def get_user_db(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncIterator[SQLAlchemyUserDatabase[UserRow, uuid.UUID]]:
    yield SQLAlchemyUserDatabase(session, UserRow)


class UserManager(UUIDIDMixin, BaseUserManager[UserRow, uuid.UUID]):
    """Password hashing and lifecycle hooks for the one identity kind here.

    No registration route is mounted (``app/web/routes/api/auth.py``), so
    ``on_after_register`` only ever fires for the seeded developer account
    (:func:`app.auth.seed.seed_dev_user`).
    """

    @property
    def reset_password_token_secret(self) -> str:
        return get_settings().auth_secret_key.get_secret_value()

    @property
    def verification_token_secret(self) -> str:
        return get_settings().auth_secret_key.get_secret_value()

    async def on_after_register(self, user: UserRow, request: object = None) -> None:
        logger.info("Professor account registered: %s", user.email)


async def get_user_manager(
    user_db: Annotated[SQLAlchemyUserDatabase[UserRow, uuid.UUID], Depends(get_user_db)],
) -> AsyncIterator[UserManager]:
    yield UserManager(user_db)
