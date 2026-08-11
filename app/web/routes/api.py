"""JSON API.

Small on purpose: health and a configuration summary used by the dashboard and
by tests. Feature endpoints arrive with the features themselves.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.llm import describe_availability
from app.persistence.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])

#: Request-scoped database session.
DbSession = Annotated[Session, Depends(get_session)]


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database_ok: bool
    llm_configured: bool
    llm_status: str


@router.get("/health", response_model=HealthResponse)
def health(session: DbSession) -> HealthResponse:
    """Liveness plus a real database round-trip."""
    settings = get_settings()
    try:
        session.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        # Health must report a problem, not raise one.
        logger.exception("Health check database probe failed")
        database_ok = False

    llm_configured, llm_status = describe_availability(settings)
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        version=__version__,
        environment=settings.environment.value,
        database_ok=database_ok,
        llm_configured=llm_configured,
        llm_status=llm_status,
    )
