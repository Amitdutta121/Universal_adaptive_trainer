"""Choose where code runs, once, from settings (C6).

The graders take their executor from :func:`graders.set_executor`; this is the one place the app
makes that choice, so scoring and the authoring checks always agree on local vs. sandbox.

``EXECUTOR=local`` runs student code in a plain subprocess of the server, so it is refused when
``ENVIRONMENT=production`` (C9); development and test keep it as the default.
"""

from __future__ import annotations

import logging

from app.config import Environment, Settings
from app.errors import ConfigurationError
from graders import set_executor

logger = logging.getLogger(__name__)


def configure_executor(settings: Settings) -> None:
    if settings.executor == "piston":
        from graders.executors.piston import PistonExecutor

        url = settings.piston_url
        set_executor(lambda: PistonExecutor(base_url=url))
        logger.info("Code runs in the Piston sandbox at %s.", url)
    else:
        if settings.environment is Environment.PRODUCTION:
            raise ConfigurationError(
                "EXECUTOR=local runs student code unsandboxed on the server and is not allowed "
                "when ENVIRONMENT=production; set EXECUTOR=piston and PISTON_URL."
            )
        set_executor(None)
        logger.warning("Code runs in a local subprocess (EXECUTOR=local); this is not a sandbox.")
