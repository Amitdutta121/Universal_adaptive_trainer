"""Whether LLM-backed features can run at all, and how to say so honestly.

Split out of the package ``__init__`` so :mod:`app.llm.client` can call
:func:`require_llm` without importing the package that imports it.

The application must start and serve every page with no credentials configured
(ADR-010), so "not configured" is a displayed state rather than a crash. These
two functions are how that state is reported and enforced.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.errors import ConfigurationError


def describe_availability(settings: Settings | None = None) -> tuple[bool, str]:
    """Return ``(configured, human_readable_status)`` for display in the UI.

    Never returns the API key or any part of it.
    """
    settings = settings or get_settings()
    return settings.llm_configured, settings.describe_llm()


def require_llm(settings: Settings | None = None) -> Settings:
    """Return settings, raising if LLM features cannot run.

    Call this at the start of any LLM-backed operation, before any work is done,
    so an unconfigured run fails immediately rather than half way through.

    Raises:
        ConfigurationError: if no provider or no credentials are configured.
    """
    settings = settings or get_settings()
    if not settings.llm_configured:
        raise ConfigurationError(
            "This feature needs an LLM provider and API key.",
            detail=(
                "Set LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in your .env file (see .env.example)."
            ),
        )
    return settings
