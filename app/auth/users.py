"""The professor user table, its manager, and the FastAPI dependencies that build them."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, InvalidPasswordException, UUIDIDMixin, schemas
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.email import send_password_reset_email, send_verification_email
from app.config import get_settings
from app.persistence.async_database import get_async_session
from app.persistence.models import AccessTokenRow, UserRow

logger = logging.getLogger(__name__)

#: Shortest password any account may have, however it is created.
MIN_PASSWORD_LENGTH = 12
#: Lifetime of an email-verification or password-reset link.
TOKEN_LIFETIME_SECONDS = 60 * 60


async def get_user_db(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncIterator[SQLAlchemyUserDatabase[UserRow, uuid.UUID]]:
    yield SQLAlchemyUserDatabase(session, UserRow)


class UserManager(UUIDIDMixin, BaseUserManager[UserRow, uuid.UUID]):
    """Password hashing and lifecycle hooks for the one identity kind here.

    Accounts come from public registration (``POST /api/auth/register``, ADR-061), from
    ``python -m app.auth.create_user`` and, in development only, from the seeded developer
    account (:func:`app.auth.seed.seed_dev_user`). The last two are created verified. A
    registered account is verified on creation unless ``REQUIRE_EMAIL_VERIFICATION`` is on, in
    which case it is sent a verification link straight away.
    """

    #: Both links work for an hour; the email text (``app/auth/email.py``) says so.
    verification_token_lifetime_seconds = TOKEN_LIFETIME_SECONDS
    reset_password_token_lifetime_seconds = TOKEN_LIFETIME_SECONDS

    @property
    def reset_password_token_secret(self) -> str:
        return get_settings().auth_secret_key.get_secret_value()

    @property
    def verification_token_secret(self) -> str:
        return get_settings().auth_secret_key.get_secret_value()

    async def validate_password(
        self, password: str, user: schemas.BaseUserCreate | UserRow
    ) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidPasswordException(
                reason=f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )

    async def on_after_register(self, user: UserRow, request: Request | None = None) -> None:
        logger.info("Professor account registered: %s", user.email)
        if not user.is_active or user.is_verified:
            return
        if get_settings().require_email_verification:
            await self.request_verify(user, request)
        else:
            await self.user_db.update(user, {"is_verified": True})
            logger.info("Verified %s on creation (REQUIRE_EMAIL_VERIFICATION is off)", user.email)

    async def on_after_request_verify(
        self, user: UserRow, token: str, request: Request | None = None
    ) -> None:
        send_verification_email(user.email, token)

    async def on_after_verify(self, user: UserRow, request: Request | None = None) -> None:
        logger.info("Professor account verified: %s", user.email)

    async def on_after_forgot_password(
        self, user: UserRow, token: str, request: Request | None = None
    ) -> None:
        send_password_reset_email(user.email, token)

    async def on_after_reset_password(self, user: UserRow, request: Request | None = None) -> None:
        """Log out every session of the account, so a stolen cookie dies with the old password."""
        session = cast(SQLAlchemyUserDatabase[UserRow, uuid.UUID], self.user_db).session
        await session.execute(delete(AccessTokenRow).where(AccessTokenRow.user_id == user.id))
        await session.commit()
        logger.info("Password reset for %s; its sessions were revoked", user.email)


async def get_user_manager(
    user_db: Annotated[SQLAlchemyUserDatabase[UserRow, uuid.UUID], Depends(get_user_db)],
) -> AsyncIterator[UserManager]:
    yield UserManager(user_db)
