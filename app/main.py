"""Application entry point.

``create_app()`` builds the FastAPI application; ``app`` is the ASGI object that
uvicorn imports (``app.main:app``). Startup work that must not run at import
time lives in the lifespan handler.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.persistence.database import init_db
from app.web.middleware import RequestLoggingMiddleware
from app.web.routes import api_router, pages_router
from app.web.templating import STATIC_DIR

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepare storage and report configuration on startup."""
    settings: Settings = app.state.settings
    init_db()
    logger.info(
        "%s v%s ready (environment=%s, llm=%s)",
        settings.app_name,
        __version__,
        settings.environment.value,
        settings.describe_llm(),
    )
    yield
    logger.info("%s shutting down", settings.app_name)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Adaptive Python training platform: professor content generation "
            "and student adaptive training."
        ),
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(RequestLoggingMiddleware)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(pages_router)
    app.include_router(api_router)

    register_error_handlers(app)
    return app


app = create_app()
