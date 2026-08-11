"""Logging setup.

A single ``dictConfig`` call owns logging for the whole process, including
uvicorn's loggers, so that application and server output share one format.
Modules should use ``logging.getLogger(__name__)`` and never configure handlers
themselves.
"""

from __future__ import annotations

import logging
from logging.config import dictConfig

from app.config import Settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(settings: Settings, *, force: bool = False) -> None:
    """Configure process-wide logging. Idempotent unless ``force`` is set."""
    global _configured
    if _configured and not force:
        return

    level = settings.log_level if settings.log_level in logging.getLevelNamesMapping() else "INFO"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {"format": LOG_FORMAT, "datefmt": DATE_FORMAT},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                # Application logger tree.
                "app": {"handlers": ["console"], "level": level, "propagate": False},
                # Align uvicorn with our format instead of its own.
                "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.error": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.access": {"handlers": ["console"], "level": level, "propagate": False},
                # SQL echo is controlled by DATABASE_ECHO, not by log level.
                "sqlalchemy.engine": {
                    "handlers": ["console"],
                    "level": "INFO" if settings.database_echo else "WARNING",
                    "propagate": False,
                },
            },
        }
    )
    _configured = True

    logging.getLogger("app").debug(
        "Logging configured (level=%s, environment=%s)", level, settings.environment.value
    )
