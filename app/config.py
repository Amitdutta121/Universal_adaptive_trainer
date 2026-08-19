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
from typing import Annotated

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    embedding_model: str = "openai/text-embedding-3-small"
    validation_timeout_seconds: float = Field(default=2.0, gt=0)

    # -- Bulk judge re-run (ADR-030) ----------------------------------------
    # OpenRouter's batch jobs are asynchronous and live under /api/beta, not
    # under the /api/v1 path the synchronous client uses. Off by default: a run
    # costs real money and completes over hours, so it is opted into.
    judge_batch_enabled: bool = False
    judge_batch_base_url: str = "https://openrouter.ai/api/beta"
    #: Falls back to ``llm_model`` so the re-run judges with the same route that
    #: generation used unless a cheaper one is named deliberately.
    judge_batch_model: str | None = None
    #: Falls back to ``llm_api_key``. Separate so a batch-scoped key can be used.
    judge_batch_api_key: SecretStr | None = None
    #: Requests per provider job. A larger bank is split across several jobs
    #: under one run id rather than submitted as one oversized body.
    judge_batch_max_requests_per_job: int = Field(default=200, gt=0)
    judge_batch_timeout_seconds: float = Field(default=120.0, gt=0)

    #: Sampling temperature for judge calls. Zero by default: a judge is a
    #: measuring instrument, and the OpenAI default of 1.0 was measured here to
    #: flip 20% of verdicts between runs of the *same* prompt on the *same*
    #: question -- enough to manufacture the disagreements that trigger a repair.
    judge_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    # -- Learning loops (ADR-042) -------------------------------------------
    # Both loops can be frozen independently. A judge cannot be measured while
    # the generator is also adapting: the question population moves under the
    # measurement, and no agreement change can be attributed to either.
    judge_learning_enabled: bool = True
    generator_learning_enabled: bool = True

    #: Disagreements naming one judge before its prompt may be rewritten.
    #: Rewriting on a single case was measured to produce a rule about that one
    #: question ("do not report technically_incorrect if swapping logic in an
    #: operation is correct"), which is overfitting, not learning.
    judge_repair_min_disagreements: int = Field(default=5, gt=0)

    #: Score a rewritten judge before adopting it, and keep it only if it does
    #: not lose. Every published prompt optimiser does this -- GEPA's minibatch
    #: acceptance, MIPRO's validation search, OPRO's scored meta-prompt. Applying
    #: an unscored candidate is mutation without selection, which is drift.
    judge_repair_gate_enabled: bool = True
    #: Held-out pairs a candidate is scored on. Each costs one judge call per
    #: prompt, so this is the cost dial for the gate.
    judge_repair_scoring_pairs: int = Field(default=8, gt=0)
    #: Below this many held-out pairs the gate cannot tell a real improvement
    #: from judge noise, so the repair is refused rather than applied blind.
    judge_repair_min_scoring_pairs: int = Field(default=5, gt=0)

    # -- Book ingestion -----------------------------------------------------
    book_upload_dir: Path = PROJECT_ROOT / "data" / "books"
    max_book_upload_mb: int = Field(default=100, gt=0)

    # -- Auth (app/auth/) -----------------------------------------------------
    #: Signs password-reset/verification tokens. Neither flow is exposed by any
    #: route yet, but fastapi-users requires the secret to exist regardless.
    #: Generate a real value for anything beyond a single developer's machine.
    auth_secret_key: SecretStr = SecretStr("dev-only-insecure-secret-change-me")
    #: The one seeded professor account (app/auth/seed.py). Only created when
    #: ENVIRONMENT=development -- a production run never seeds a credential.
    dev_user_email: str = "dev@local.test"
    dev_user_password: SecretStr = SecretStr("devpassword123")

    # -- Browser clients ----------------------------------------------------
    # Origins allowed to call /api from a browser. Defaults cover the Vite and
    # create-react-app development servers; set explicitly in production.
    # ``NoDecode`` keeps pydantic-settings from JSON-decoding the raw value so
    # that a plain comma-separated list works in a ``.env`` file.
    cors_allow_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator(
        "llm_api_key", "llm_base_url", "judge_batch_api_key", "judge_batch_model", mode="before"
    )
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        """Treat ``KEY=`` in a ``.env`` file as "not configured"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept ``CORS_ALLOW_ORIGINS=http://a,http://b`` from the environment."""
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
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

    @property
    def judge_batch_route(self) -> str:
        """The model the bulk judge re-run submits under."""
        return self.judge_batch_model or self.llm_model

    @property
    def judge_batch_credential(self) -> SecretStr | None:
        """The key the bulk judge re-run authenticates with, or ``None``."""
        return self.judge_batch_api_key or self.llm_api_key

    def describe_judge_batch(self) -> str:
        """Human-readable batch re-run status. Never leaks the credential."""
        if not self.judge_batch_enabled:
            return "disabled (JUDGE_BATCH_ENABLED=false)"
        if self.judge_batch_credential is None:
            return f"{self.judge_batch_route} (no API key configured)"
        return self.judge_batch_route

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
