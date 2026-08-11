"""Application configuration.

All runtime configuration is read from environment variables (optionally via a
local ``.env`` file). Nothing else in the codebase should read ``os.environ``
directly -- import :func:`get_settings` instead so that tests can override
configuration in one place.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Environment(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LLMProvider(StrEnum):
    """Supported LLM providers.

    ``NONE`` keeps the UI runnable without credentials (ADR-010).
    ``OPENROUTER`` is the only live transport (ADR-020): DeepSeek and other
    routes are selected with ``LLM_MODEL``, not with extra provider values.
    """

    OPENROUTER = "openrouter"
    NONE = "none"


class Settings(BaseSettings):
    """Typed application settings.

    Values come from (in order of precedence) constructor arguments, process
    environment variables, then a ``.env`` file in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Application / development settings ---------------------------------
    app_name: str = "Adaptive Trainer"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"

    # -- Persistence --------------------------------------------------------
    database_url: str = "sqlite:///./data/adaptive_trainer.db"
    database_echo: bool = False

    # -- LLM provider -------------------------------------------------------
    llm_provider: LLMProvider = LLMProvider.OPENROUTER
    llm_model: str = "deepseek/deepseek-chat"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_output_tokens: int = Field(default=4096, gt=0)
    validation_timeout_seconds: float = Field(default=2.0, gt=0)

    # -- Book ingestion -----------------------------------------------------
    book_upload_dir: Path = PROJECT_ROOT / "data" / "books"
    max_book_upload_mb: int = Field(default=100, gt=0)

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("llm_api_key", "llm_base_url", mode="before")
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        """Treat ``KEY=`` in a ``.env`` file as "not configured"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def llm_configured(self) -> bool:
        """True when an LLM provider *and* credentials are both available.

        LLM-backed features (question generation and later LLM features) must
        check this and degrade gracefully instead of raising at import time.
        """
        return self.llm_provider is not LLMProvider.NONE and self.llm_api_key is not None

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT

    def describe_llm(self) -> str:
        """Human-readable LLM status for the UI. Never leaks the credential."""
        if self.llm_provider is LLMProvider.NONE:
            return "disabled (LLM_PROVIDER=none)"
        if self.llm_api_key is None:
            return f"{self.llm_provider.value}/{self.llm_model} (no API key configured)"
        return f"{self.llm_provider.value}/{self.llm_model}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that configuration is parsed once. Tests that need different
    values should call ``get_settings.cache_clear()`` or construct ``Settings``
    directly.
    """
    return Settings()
