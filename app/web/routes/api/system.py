"""System endpoints: liveness, client configuration and dashboard counts."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.curriculum.taxonomy_schema import SCHEMA_VERSION as TAXONOMY_SCHEMA_VERSION
from app.ingestion import SCHEMA_VERSION as BOOK_SCHEMA_VERSION
from app.ingestion import SUPPORTED_EXTENSIONS
from app.llm import describe_availability
from app.persistence.repositories import (
    BookRepository,
    CurriculumRepository,
    PreferenceRepository,
    ProfessorReviewRepository,
    QuestionRepository,
)
from app.web.routes.api.deps import DbSession
from app.web.routes.api.schemas import ConfigResponse, CountsResponse, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


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


@router.get("/config", response_model=ConfigResponse)
def config() -> ConfigResponse:
    """Enum vocabularies and limits, so a client never hard-codes them."""
    settings = get_settings()
    llm_configured, llm_status = describe_availability(settings)
    return ConfigResponse.build(
        app_name=settings.app_name,
        version=__version__,
        environment=settings.environment.value,
        llm_configured=llm_configured,
        llm_status=llm_status,
        llm_model=settings.llm_model,
        embedding_model=settings.embedding_model,
        book_schema_version=BOOK_SCHEMA_VERSION,
        taxonomy_schema_version=TAXONOMY_SCHEMA_VERSION,
        supported_book_extensions=SUPPORTED_EXTENSIONS,
        max_book_upload_mb=settings.max_book_upload_mb,
    )


@router.get("/counts", response_model=CountsResponse)
def counts(session: DbSession) -> CountsResponse:
    """One count per section. ``students`` stays 0 until the adaptive engine exists."""
    return CountsResponse(
        books=BookRepository(session).count(),
        curriculum_versions=CurriculumRepository(session).count(),
        questions=QuestionRepository(session).count(),
        reviews=ProfessorReviewRepository(session).count(),
        preferences=len(PreferenceRepository(session).list_all()),
        students=0,
    )
