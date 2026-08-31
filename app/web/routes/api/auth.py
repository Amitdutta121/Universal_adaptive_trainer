"""Login/logout for the Instructor Studio, and a "who am I" check.

No registration route is mounted here: this application has one identity
kind, seeded on startup (``app/auth/seed.py``), not created through signup.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.backend import auth_backend, current_active_user, fastapi_users
from app.persistence.models import UserRow

router = APIRouter(prefix="/auth", tags=["auth"])
router.include_router(fastapi_users.get_auth_router(auth_backend))


@router.get("/me")
def read_current_user(user: Annotated[UserRow, Depends(current_active_user)]) -> dict[str, str]:
    """The frontend's session check: 401 with no cookie, the professor's identity otherwise."""
    return {"id": str(user.id), "email": user.email}
