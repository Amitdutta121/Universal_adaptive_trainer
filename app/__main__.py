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
        # Scope the watch to our own source tree. The default watch root is cwd,
        # which also covers frontend/ -- next dev's continuous writes to
        # frontend/.next during compilation/HMR were registering as file changes
        # and retriggering backend reloads in an unbroken storm.
        reload_dirs=["app"] if settings.is_development else None,
        # Dev convention redirects this process's own stdout/stderr to *_fresh_*.log
        # files at the repo root -- inside the default watch root. Without this
        # exclusion, every log write is a file change, which triggers another
        # reload, which writes more log lines: a self-sustaining reload storm that
        # piles up duplicate worker processes on the same port.
        reload_excludes=["*_fresh_*.log"] if settings.is_development else None,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
