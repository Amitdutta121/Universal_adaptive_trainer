"""Shared dependencies for the JSON API routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.persistence.database import get_session

#: Request-scoped database session.
DbSession = Annotated[Session, Depends(get_session)]
