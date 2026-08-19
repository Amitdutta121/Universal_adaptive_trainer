"""The one seeded developer account.

There is no public registration route (``app/web/routes/api/auth.py``), so
this is the only way a professor identity comes to exist outside a
production deployment, which must set its own credentials and never runs
this. See ``docs/DECISIONS.md`` for why: a hardcoded credential must not ship
live by accident.
"""

from __future__ import annotations

import logging

from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.password import PasswordHelper
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import UserManager
from app.config import Environment, Settings
from app.persistence.async_database import get_async_session_factory
from app.persistence.models import UserRow

logger = logging.getLogger(__name__)


async def seed_dev_user(settings: Settings) -> None:
    """Create the developer account on startup, only in ``ENVIRONMENT=development``."""
    if settings.environment is not Environment.DEVELOPMENT:
        return

    async with get_async_session_factory()() as session:
        await _seed(session, settings)


async def _seed(session: AsyncSession, settings: Settings) -> None:
    user_db = SQLAlchemyUserDatabase(session, UserRow)
    manager = UserManager(user_db, password_helper=PasswordHelper())
    email = settings.dev_user_email
    try:
        await manager.create(
            _DevUserCreate(email=email, password=settings.dev_user_password.get_secret_value())
        )
    except UserAlreadyExists:
        return
    logger.info("Seeded developer account %s (ENVIRONMENT=development only).", email)


class _DevUserCreate:
    """The minimal shape ``BaseUserManager.create`` reads off a "user create" object.

    Avoids depending on the Pydantic schema defined in
    ``app/web/routes/api/auth.py`` just to seed one row at startup.
    """

    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password
        self.is_active = True
        self.is_superuser = False
        self.is_verified = True

    def create_update_dict(self) -> dict[str, object]:
        return {
            "email": self.email,
            "password": self.password,
            "is_active": True,
            "is_verified": True,
        }

    def create_update_dict_superuser(self) -> dict[str, object]:
        return self.create_update_dict()
