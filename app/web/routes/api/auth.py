"""Professor accounts: login/logout, public registration, email verification, password reset.

All of it is fastapi-users' own routers (ADR-061); nothing here hand-rolls a signup step.

- ``POST /register`` creates an active, *unverified* account and emails a verification link.
  It runs ``create(safe=True)``, so a posted ``is_superuser``, ``is_verified`` or ``is_active``
  is ignored. An existing email is a 400, which does reveal that the address has an account.
- ``POST /request-verify-token`` and ``POST /verify`` send and redeem that link.
- ``POST /forgot-password`` answers 202 whether or not the email has an account;
  ``POST /reset-password`` redeems the emailed token.

An unverified account can log in and use the Studio; only the routes that spend LLM or
embedder credit require a verified one (:func:`app.auth.backend.current_verified_user`).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_users import schemas
from pydantic import BaseModel, EmailStr

from app.auth.backend import auth_backend, current_active_user, fastapi_users
from app.persistence.models import UserRow


class UserRead(schemas.BaseUser[uuid.UUID]):
    """The account as the API shows it."""


class UserCreate(schemas.CreateUpdateDictModel):
    """What a registration posts: an email and a password, nothing else.

    Narrower than ``BaseUserCreate``, so the public schema does not even list
    ``is_superuser``/``is_verified``/``is_active``. A body that sends them anyway has them
    ignored here, and ``create(safe=True)`` would drop them regardless.
    """

    email: EmailStr
    password: str


router = APIRouter(prefix="/auth", tags=["auth"])
router.include_router(fastapi_users.get_auth_router(auth_backend))
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))  # type: ignore[type-var]
router.include_router(fastapi_users.get_verify_router(UserRead))
router.include_router(fastapi_users.get_reset_password_router())


class CurrentUserOut(BaseModel):
    """``/me``. A plain ``str`` email, unlike :class:`UserRead`: the seeded developer account's
    ``dev@local.test`` is not a deliverable address and must still be readable."""

    id: uuid.UUID
    email: str
    is_verified: bool


@router.get("/me", response_model=CurrentUserOut)
def read_current_user(user: Annotated[UserRow, Depends(current_active_user)]) -> CurrentUserOut:
    """The frontend's session check: 401 with no cookie, the professor's account otherwise.

    ``is_verified`` drives the Studio's "verify your email" banner.
    """
    return CurrentUserOut(id=user.id, email=user.email, is_verified=user.is_verified)
