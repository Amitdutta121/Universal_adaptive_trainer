"""Run the development server: ``python -m app``.

Reads host, port, log level and reload behaviour from settings so there is one
way to start the app locally.
"""

from __future__ import annotations

import uvicorn

from app.config import get_settings
from app.logging_config import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
