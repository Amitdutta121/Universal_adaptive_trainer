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
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.auth.seed import seed_dev_user
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.persistence.database import init_db
from app.web.middleware import RequestLoggingMiddleware
from app.web.routes import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepare storage and report configuration on startup."""
    settings: Settings = app.state.settings
    init_db()
    await seed_dev_user(settings)
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
    if settings.cors_allow_origins:
        # Added last so it is the outermost middleware: an error response must
        # still carry the CORS headers, or the browser reports a CORS failure
        # instead of the actual status the API returned.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(api_router)

    register_error_handlers(app)
    return app


app = create_app()
