"""The cookie transport, the database session strategy, and ``current_active_user``.

The strategy is database-backed (an :class:`~app.persistence.models.AccessTokenRow`
per login) rather than JWT: logout deletes the row, so a copied cookie value
stops working immediately instead of surviving until a token's expiry.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import AccessTokenDatabase, DatabaseStrategy
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import get_user_manager
from app.config import get_settings
from app.persistence.async_database import get_async_session
from app.persistence.models import AccessTokenRow, UserRow

#: How long a login stays valid without re-authenticating.
SESSION_LIFETIME_SECONDS = 60 * 60 * 12

COOKIE_NAME = "atsession"


async def get_access_token_db(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncIterator[SQLAlchemyAccessTokenDatabase[AccessTokenRow]]:
    yield SQLAlchemyAccessTokenDatabase(session, AccessTokenRow)


def get_database_strategy(
    access_token_db: Annotated[AccessTokenDatabase[AccessTokenRow], Depends(get_access_token_db)],
) -> DatabaseStrategy[UserRow, uuid.UUID, AccessTokenRow]:
    return DatabaseStrategy(access_token_db, lifetime_seconds=SESSION_LIFETIME_SECONDS)


cookie_transport = CookieTransport(
    cookie_name=COOKIE_NAME,
    cookie_max_age=SESSION_LIFETIME_SECONDS,
    # Plain HTTP in development (no TLS on localhost); the frontend rewrite
    # (`frontend/next.config.ts`) keeps every request same-origin regardless,
    # so `samesite="lax"` is enough -- this only needs to loosen for HTTPS.
    cookie_secure=not get_settings().is_development,
    cookie_samesite="lax",
)

auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)

fastapi_users = FastAPIUsers[UserRow, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
